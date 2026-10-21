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
from app.adapters.patterns.base import GraphFactory, TraceContextFactory
from app.adapters.patterns.registry import PATTERN_NAMES, build_patterns
from app.adapters.persistence.tickets import RepositoryTicketReader
from app.application.chat import SendChatMessage
from app.application.conversations import ConversationRegistry
from app.application.tickets import ListCustomerTickets
from app.settings import Settings, load_settings

MESSAGES_PER_MINUTE = 20


def build_chat_app(
    *,
    session_guard: SessionGuard | None = None,
    graph_factories: Mapping[str, GraphFactory] | None = None,
    settings_factory: Callable[[], Settings] = load_settings,
    trace_context_factory: TraceContextFactory | None = None,
    ticket_repository_factory: Callable[[], Any] | None = None,
) -> FastAPI:
    app = FastAPI(title="TechFix.AI · Patrones LangGraph", version="1.1.0")
    account_settings = session_guard.settings if session_guard is not None else AccountSettings.from_env()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(account_settings.frontend_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "Accept"],
    )
    app.add_exception_handler(
        SessionError,
        lambda _request, exc: JSONResponse(status_code=exc.status, content={"detail": exc.detail, "code": exc.code}),
    )
    app.add_exception_handler(RequestValidationError, lambda _request, exc: _validation_response(exc))

    # La sesión se resuelve al primer uso para que importar el módulo no exija AUTH_SECRET.
    guard_holder: dict[str, SessionGuard | None] = {"guard": session_guard}

    def require_customer(request: Request) -> SessionCustomer:
        if guard_holder["guard"] is None:
            guard_holder["guard"] = SessionGuard.from_env()
        return guard_holder["guard"].require_customer(request)

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
    app.include_router(
        create_chat_router(
            send_message=send_message,
            list_tickets=list_tickets,
            require_customer=require_customer,
            pattern_names=PATTERN_NAMES,
        )
    )
    return app
