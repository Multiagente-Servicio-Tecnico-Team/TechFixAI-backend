"""Unified ASGI entry point for account, customer and administrator APIs."""
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI
from sqlalchemy.orm import sessionmaker

from app.accounts.api import create_app as create_accounts_app
from app.accounts.config import Settings as AccountSettings
from app.accounts.session import SessionGuard
from app.adapters.api.customers import create_customer_router
from app.adapters.llm.tracing import get_trace_context, redact_trace_error
from app.adapters.patterns.base import GraphFactory, TraceContextFactory
from app.adapters.patterns.registry import PATTERN_NAMES
from app.infrastructure.chat_app import build_chat_app
from app.settings import Settings, load_settings

PROJECT_ROOT = Path(__file__).resolve().parents[1]
__all__ = ["PATTERN_NAMES", "app", "create_app", "get_trace_context", "redact_trace_error"]


def create_app(
    settings: AccountSettings | None = None,
    session_factory: sessionmaker | None = None,
    mailer: Any | None = None,
    *,
    chat_app: FastAPI | None = None,
    session_guard: SessionGuard | None = None,
    graph_factories: Mapping[str, GraphFactory] | None = None,
    settings_factory: Callable[[], Settings] = load_settings,
    trace_context_factory: TraceContextFactory | None = None,
    ticket_repository_factory: Callable[[], Any] | None = None,
    accounting_repository_factory: Callable[[], Any] | None = None,
    inventory_repository_factory: Callable[[], Any] | None = None,
    purchase_repository_factory: Callable[[], Any] | None = None,
    purchase_order_repository_factory: Callable[[], Any] | None = None,
    sales_repository_factory: Callable[[], Any] | None = None,
    customer_repository_factory: Callable[[], Any] | None = None,
) -> FastAPI:
    """Compose the account app and chat/admin API exactly once.

    Positional `settings` and `session_factory` remain supported by the existing
    account API integration. Chat routes and all administrative routes are
    composed by `build_chat_app`; this module only mounts authentication and
    the customer directory route.
    """
    load_dotenv(dotenv_path=PROJECT_ROOT / ".env", override=False)
    account_settings = settings or (
        session_guard.settings if session_guard is not None else AccountSettings.from_env()
    )
    accounts_app = create_accounts_app(
        settings=account_settings,
        session_factory=(
            session_factory
            or (session_guard.session_factory if session_guard is not None else None)
        ),
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
        accounting_repository_factory=accounting_repository_factory,
        inventory_repository_factory=inventory_repository_factory,
        purchase_repository_factory=purchase_repository_factory,
        purchase_order_repository_factory=purchase_order_repository_factory,
        sales_repository_factory=sales_repository_factory,
        customer_repository_factory=customer_repository_factory,
    )
    application.mount("/auth", accounts_app)
    application.include_router(
        create_customer_router(require_admin=shared_guard.require_admin)
    )
    return application


app = create_app()
