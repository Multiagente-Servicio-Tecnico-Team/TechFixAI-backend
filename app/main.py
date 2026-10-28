"""Punto único de entrada de la API unificada (`app.main:app`).

La lógica vive en las capas de Clean Architecture:
- `app/domain`: entidades y reglas (presupuesto, ticket, conversación).
- `app/application`: casos de uso y puertos.
- `app/adapters`: FastAPI, patrones LangGraph, PostgreSQL y LangSmith.
- `app/infrastructure`: raíz de composición.
Monta autenticación bajo `/auth/*` y chat bajo `/api/*`, compartiendo la
configuración y fábrica SQLAlchemy de cuentas con la validación de sesión.
"""
from collections.abc import Callable, Mapping
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI
from sqlalchemy.orm import sessionmaker

from app.accounts.api import create_app as create_accounts_app
from app.accounts.config import Settings as AccountSettings
from app.accounts.session import SessionGuard
from app.adapters.llm.tracing import get_trace_context, redact_trace_error
from app.adapters.patterns.base import GraphFactory, TraceContextFactory
from app.adapters.patterns.registry import PATTERN_NAMES
from app.infrastructure.chat_app import build_chat_app
from app.settings import Settings, load_settings

__all__ = ["PATTERN_NAMES", "app", "create_app", "get_trace_context", "redact_trace_error"]


def create_app(
    *,
    settings: AccountSettings | None = None,
    session_factory: sessionmaker | None = None,
    mailer=None,
    chat_app: FastAPI | None = None,
    session_guard: SessionGuard | None = None,
    graph_factories: Mapping[str, GraphFactory] | None = None,
    settings_factory: Callable[[], Settings] = load_settings,
    trace_context_factory: TraceContextFactory | None = None,
    ticket_repository_factory: Callable[[], Any] | None = None,
) -> FastAPI:
    load_dotenv()
    account_settings = settings or (session_guard.settings if session_guard else AccountSettings.from_env())
    accounts_app = create_accounts_app(
        settings=account_settings,
        session_factory=session_factory or (session_guard.session_factory if session_guard else None),
        mailer=mailer,
    )
    shared_guard = session_guard or SessionGuard(
        account_settings,
        accounts_app.state.session_factory,
    )
    application = chat_app or build_chat_app(
        session_guard=shared_guard,
        graph_factories=graph_factories,
        settings_factory=settings_factory,
        trace_context_factory=trace_context_factory,
        ticket_repository_factory=ticket_repository_factory,
    )
    application.mount("/auth", accounts_app)
    return application


app = create_app()
