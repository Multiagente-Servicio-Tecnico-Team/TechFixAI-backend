"""Raíz de composición del chat: conecta adaptadores, casos de uso y rutas.

Es el único lugar que conoce las implementaciones concretas; el resto de capas
depende de los puertos de `app.application.ports`.
"""
from collections.abc import Callable, Mapping
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.accounts.api import _validation_response
from app.accounts.config import Settings as AccountSettings
from app.accounts.security import LoginLimiter
from app.accounts.session import SessionCustomer, SessionError, SessionGuard
from app.adapters.api.chat import create_chat_router
from app.adapters.api.admin_tickets import create_admin_ticket_router
from app.adapters.api.accounting import create_accounting_router
from app.adapters.speech.groq import GroqAudioTranscriber
from app.adapters.patterns.base import GraphFactory, TraceContextFactory
from app.adapters.patterns.registry import PATTERN_NAMES, build_patterns
from app.adapters.persistence.tickets import RepositoryTicketReader
from app.adapters.persistence.accounting import AccountingRepositoryAdapter
from app.application.chat import SendChatMessage
from app.application.audio_chat import SendAudioChatMessage
from app.application.audio_requests import AudioRequestRegistry
from app.application.ports import AudioTranscriber
from app.application.conversations import ConversationRegistry
from app.application.tickets import ListCustomerTickets
from app.settings import Settings, load_settings
from app.infrastructure.decentralized_runtime import create_lifespan
from app.adapters.patterns.durable_conversations import DurableConversations
from app.infrastructure.request_limits import RequestBodyLimitMiddleware

MESSAGES_PER_MINUTE = 20


def build_chat_app(
    *,
    session_guard: SessionGuard | None = None,
    graph_factories: Mapping[str, GraphFactory] | None = None,
    settings_factory: Callable[[], Settings] = load_settings,
    trace_context_factory: TraceContextFactory | None = None,
    ticket_repository_factory: Callable[[], Any] | None = None,
    audio_transcriber: AudioTranscriber | None = None,
    accounting_repository_factory: Callable[[], Any] | None = None,
    checkpoint_resources_factory=None,
    financial_repository=None,
    conversation_owners_repository=None,
    conversation_locks=None,
) -> FastAPI:
    app = FastAPI(title="TechFix.AI · Patrones LangGraph", version="1.1.0", lifespan=create_lifespan(
        graph_factories=graph_factories, checkpoint_resources_factory=checkpoint_resources_factory, financial_repository=financial_repository))
    app.state.decentralized_graph = None
    app.state.checkpoint_resources = None
    app.state.conversation_owners = conversation_owners_repository
    app.state.conversation_locks = conversation_locks
    runtime_settings = settings_factory()
    account_settings = session_guard.settings if session_guard is not None else AccountSettings.from_env()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(account_settings.frontend_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "Accept", "Idempotency-Key"],
    )
    app.add_middleware(RequestBodyLimitMiddleware, max_bytes=runtime_settings.audio_max_bytes + 100_000)

    @app.middleware("http")
    async def accounting_no_store(request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/api/admin/accounting/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    app.add_exception_handler(
        SessionError,
        lambda _request, exc: JSONResponse(status_code=exc.status, content={"detail": exc.detail, "code": exc.code}),
    )
    def validation_response(request: Request, exc: RequestValidationError):
        if request.url.path.startswith("/api/admin/accounting/"):
            errors = []
            for error in exc.errors():
                location = [str(part) for part in error.get("loc", ()) if part not in {"body", "query", "header", "path"}]
                errors.append({"field": ".".join(location) or None, "reason": str(error.get("msg", "Valor inválido."))})
            return JSONResponse(status_code=422, content={"detail": "Datos contables inválidos.", "code": "accounting_validation", "fields": errors})
        return _validation_response(exc)

    app.add_exception_handler(RequestValidationError, validation_response)

    # La sesión se resuelve al primer uso para que importar el módulo no exija AUTH_SECRET.
    guard_holder: dict[str, SessionGuard | None] = {"guard": session_guard}

    def require_customer(request: Request) -> SessionCustomer:
        if guard_holder["guard"] is None:
            guard_holder["guard"] = SessionGuard.from_env()
        return guard_holder["guard"].require_customer(request)

    def require_admin(request: Request) -> SessionCustomer:
        if guard_holder["guard"] is None:
            guard_holder["guard"] = SessionGuard.from_env()
        return guard_holder["guard"].require_admin(request)

    patterns = build_patterns(
        graph_factories,
        settings_factory=settings_factory,
        trace_context_factory=trace_context_factory,
    )
    app.state.patterns = patterns
    if graph_factories is None:
        def durable_graph():
            if app.state.decentralized_graph is None:
                raise StorageUnavailable()
            return app.state.decentralized_graph
        from app.application.errors import StorageUnavailable
        patterns["decentralized"]._graph_factory = durable_graph
    patterns["decentralized"].configure_runtime(graph_factories=graph_factories, financial_repository=financial_repository)
    registry = ConversationRegistry()
    durable = DurableConversations(app, patterns["decentralized"], registry,
        conversation_owners_repository, conversation_locks) if graph_factories is None or conversation_owners_repository is not None else None
    send_message = SendChatMessage(
        patterns=patterns,
        conversations=registry,
        durable_conversations=durable,
        limiter=LoginLimiter(MESSAGES_PER_MINUTE, 60),
    )
    list_tickets = ListCustomerTickets(lambda: RepositoryTicketReader(ticket_repository_factory))
    configured_transcriber = audio_transcriber
    if runtime_settings.audio_transcription_enabled and configured_transcriber is None and runtime_settings.groq_api_key:
        configured_transcriber = GroqAudioTranscriber(
            runtime_settings.groq_api_key,
            timeout=runtime_settings.audio_transcription_timeout_seconds,
        )
    audio_use_case = (
        SendAudioChatMessage(
            configured_transcriber,
            send_message,
            AudioRequestRegistry(quota=runtime_settings.audio_requests_per_minute),
            max_bytes=runtime_settings.audio_max_bytes,
            max_duration_ms=runtime_settings.audio_max_duration_ms,
        )
        if runtime_settings.audio_transcription_enabled and configured_transcriber is not None
        else None
    )
    app.include_router(
        create_chat_router(
            send_message=send_message,
            list_tickets=list_tickets,
            require_customer=require_customer,
            pattern_names=PATTERN_NAMES,
            audio_message=audio_use_case,
            audio_enabled=runtime_settings.audio_transcription_enabled,
            audio_max_bytes=runtime_settings.audio_max_bytes,
        )
    )
    app.include_router(
        create_admin_ticket_router(
            require_admin=require_admin,
            repository_factory=ticket_repository_factory,
        )
    )
    repository_factory = accounting_repository_factory or (lambda: AccountingRepositoryAdapter())
    app.include_router(create_accounting_router(repository_factory, require_admin))
    return app
