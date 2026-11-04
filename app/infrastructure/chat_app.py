"""Raíz de composición del chat: conecta adaptadores, casos de uso y rutas.

Es el único lugar que conoce las implementaciones concretas; el resto de capas
depende de los puertos de `app.application.ports`.
"""
from collections.abc import Callable, Mapping
from dataclasses import replace
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
from app.adapters.api.inventory import create_inventory_router
from app.adapters.api.purchases import create_supplier_purchase_router
from app.adapters.api.sales_quotes import create_sales_quote_router
from app.adapters.speech.groq import GroqAudioTranscriber
from app.adapters.patterns.base import GraphFactory, TraceContextFactory
from app.adapters.patterns.registry import PATTERN_NAMES, build_patterns
from app.adapters.persistence.tickets import RepositoryTicketReader
from app.adapters.persistence.customers import CustomerRepositoryAdapter
from app.database.repository import ServiceRepository
from app.adapters.persistence.accounting import AccountingRepositoryAdapter
from app.adapters.persistence.purchases import SupplierPurchaseRepositoryAdapter
from app.application.chat import SendChatMessage
from app.application.audio_chat import SendAudioChatMessage
from app.application.audio_requests import AudioRequestRegistry
from app.application.ports import AudioTranscriber
from app.application.conversations import ConversationRegistry
from app.application.tickets import ListCustomerTickets
from app.application.customer_profiles import CustomerProfileService
from app.settings import Settings, load_settings
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
    inventory_repository_factory: Callable[[], Any] | None = None,
    purchase_repository_factory: Callable[[], Any] | None = None,
    sales_repository_factory: Callable[[], Any] | None = None,
) -> FastAPI:
    app = FastAPI(title="TechFix.AI · Patrones LangGraph", version="1.1.0")
    runtime_settings = settings_factory()
    account_settings = session_guard.settings if session_guard is not None else AccountSettings.from_env()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(account_settings.frontend_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
        allow_headers=["Content-Type", "Accept", "Idempotency-Key"],
    )
    app.add_middleware(RequestBodyLimitMiddleware, max_bytes=runtime_settings.audio_max_bytes + 100_000)

    @app.middleware("http")
    async def accounting_no_store(request: Request, call_next):
        response = await call_next(request)
        if (request.url.path.startswith("/api/admin/accounting/")
                or request.url.path.startswith("/api/admin/tickets")
                or request.url.path.startswith("/api/admin/purchases")
                or request.url.path.startswith("/api/admin/suppliers")
                or request.url.path.startswith("/api/admin/sales-")):
            response.headers["Cache-Control"] = "no-store"
        return response

    app.add_exception_handler(
        SessionError,
        lambda _request, exc: JSONResponse(status_code=exc.status, content={"detail": exc.detail, "code": exc.code}),
    )
    def validation_response(request: Request, exc: RequestValidationError):
        if request.url.path.startswith("/api/inventory/"):
            errors = []
            for error in exc.errors():
                location = [str(part) for part in error.get("loc", ()) if part not in {"body", "query", "header", "path"}]
                errors.append({"field": ".".join(location) or None, "reason": str(error.get("msg", "Valor inválido."))})
            field = next((error["field"] for error in errors if error["field"]), None)
            return JSONResponse(status_code=422, content={
                "detail": "Datos del repuesto inválidos.",
                "code": "invalid",
                "field": field,
                "errors": errors,
            })
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
        user = guard_holder["guard"].require_customer(request)
        profile = CustomerProfileService(CustomerRepositoryAdapter()).resolve_session_customer(user)
        return replace(user, commercial_customer_id=int(profile["id"]))

    def require_admin(request: Request) -> SessionCustomer:
        if guard_holder["guard"] is None:
            guard_holder["guard"] = SessionGuard.from_env()
        return guard_holder["guard"].require_admin(request)

    def require_staff(request: Request) -> SessionCustomer:
        if guard_holder["guard"] is None:
            guard_holder["guard"] = SessionGuard.from_env()
        return guard_holder["guard"].require_staff(request)

    patterns = build_patterns(
        graph_factories,
        settings_factory=settings_factory,
        trace_context_factory=trace_context_factory,
    )
    send_message = SendChatMessage(
        patterns=patterns,
        conversations=ConversationRegistry(),
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
            create_portal_ticket=lambda **values: _create_portal_ticket(
                repository_factory=ticket_repository_factory, **values
            ),
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
    purchases_factory = purchase_repository_factory or (lambda: SupplierPurchaseRepositoryAdapter())
    app.include_router(create_supplier_purchase_router(require_admin=require_admin, repository_factory=purchases_factory))
    app.include_router(
        create_inventory_router(
            require_staff=require_staff,
            repository_factory=inventory_repository_factory,
        )
    )
    app.include_router(create_sales_quote_router(
        require_admin=require_admin,
        require_customer=require_customer,
        repository_factory=sales_repository_factory,
    ))
    return app


def _create_portal_ticket(*, repository_factory=None, customer_id: int, title: str,
                           failure_description: str, request_type: str) -> dict[str, Any]:
    from uuid import uuid4

    if request_type not in {"REPAIR", "SUPPORT", "PC_BUILD", "WARRANTY_CLAIM"}:
        raise ValueError("El tipo de solicitud no corresponde a un ticket de servicio.")
    repository = repository_factory() if repository_factory else ServiceRepository()
    code = f"TCK-{uuid4().hex[:12].upper()}"
    ticket_id = repository.create_intake_ticket(
        code=code, customer_id=customer_id, title=title,
        failure_description=failure_description, request_type=request_type,
    )
    return {"id": ticket_id, "code": code, "customer_id": customer_id,
            "request_type": request_type, "status": "NEW"}
