"""Punto de entrada de la API del chat (`app.main:app`).

La lógica vive en las capas de Clean Architecture:
- `app/domain`: entidades y reglas (presupuesto, ticket, conversación).
- `app/application`: casos de uso y puertos.
- `app/adapters`: FastAPI, patrones LangGraph, PostgreSQL y LangSmith.
- `app/infrastructure`: raíz de composición.
Este módulo conserva la firma de `create_app` y los nombres que ya usaban
`app.combined`, el despliegue y las pruebas.
"""
from collections.abc import Callable, Mapping
from typing import Any

from fastapi import FastAPI

from app.accounts.session import SessionGuard
from app.adapters.llm.tracing import get_trace_context, redact_trace_error
from app.adapters.patterns.base import GraphFactory, TraceContextFactory
from app.adapters.patterns.registry import PATTERN_NAMES
from app.infrastructure.chat_app import build_chat_app
from app.settings import Settings, load_settings

__all__ = ["PATTERN_NAMES", "app", "create_app", "get_trace_context", "redact_trace_error"]


def create_app(
    *,
    session_guard: SessionGuard | None = None,
    graph_factories: Mapping[str, GraphFactory] | None = None,
    settings_factory: Callable[[], Settings] = load_settings,
    trace_context_factory: TraceContextFactory | None = None,
    ticket_repository_factory: Callable[[], Any] | None = None,
) -> FastAPI:
    return build_chat_app(
        session_guard=session_guard,
        graph_factories=graph_factories,
        settings_factory=settings_factory,
        trace_context_factory=trace_context_factory,
        ticket_repository_factory=ticket_repository_factory,
    )


app = create_app()
