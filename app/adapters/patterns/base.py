"""Adaptador base de los patrones LangGraph (método plantilla).

Cada patrón conserva su grafo y su estado propios en `app/agents/`; el adaptador
los presenta a la aplicación con el puerto `ChatPattern`: arma el estado inicial,
invoca el grafo con el `thread_id` de la conversación, traduce los errores
técnicos y convierte el estado final en un `PatternReply` común.
"""
import logging
import re
from collections.abc import Callable
from contextlib import AbstractContextManager
from threading import RLock
from typing import Any

from groq import APIError as GroqAPIError
from langchain_core.exceptions import OutputParserException
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from app.adapters.llm.tracing import get_trace_context
from app.application.errors import PatternFailure, StorageUnavailable
from app.domain.chat import PatternReply
from app.settings import Settings, load_settings

logger = logging.getLogger(__name__)

GraphFactory = Callable[[], Any]
TraceContextFactory = Callable[[], AbstractContextManager[None]]
PATTERN_ERRORS = (OutputParserException, ValidationError, ValueError, LookupError, RuntimeError)


class GraphPattern:
    id: str = ""
    name: str = ""
    supports_quotes: bool = True

    def __init__(
        self,
        graph_factory: GraphFactory | None = None,
        trace_context_factory: TraceContextFactory | None = None,
        settings_factory: Callable[[], Settings] = load_settings,
    ) -> None:
        self._graph_factory = graph_factory or self.build_graph
        self._settings_factory = settings_factory
        self._trace_context_factory = trace_context_factory or (lambda: get_trace_context(settings_factory()))
        self._graph: Any = None
        self._lock = RLock()

    # Lo que cambia entre patrones -------------------------------------------------
    def build_graph(self) -> Any:
        raise NotImplementedError

    def initial_state(self, customer_id: int, message: HumanMessage) -> dict[str, Any]:
        raise NotImplementedError

    def prepare(self, graph: Any, state: dict[str, Any], config: dict[str, Any]) -> None:
        """Ajustes previos a la invocación (por defecto, ninguno)."""

    def to_reply(self, result: dict[str, Any]) -> PatternReply:
        raise NotImplementedError

    # Flujo común ------------------------------------------------------------------
    def graph(self) -> Any:
        with self._lock:
            if self._graph is None:
                self._graph = self._graph_factory()
            return self._graph

    def config(self, conversation_id: str) -> dict[str, Any]:
        return {
            "configurable": {"thread_id": conversation_id},
            "run_name": f"techfix-{self.id}",
            "tags": ["service-chat", f"pattern:{self.id}"],
            "metadata": {"pattern": self.id, "conversation_id": conversation_id},
        }

    def reply(self, conversation_id: str, customer_id: int, message: str) -> PatternReply:
        try:
            graph = self.graph()
            state = self.initial_state(customer_id, HumanMessage(content=message))
            config = self.config(conversation_id)
            self.prepare(graph, state, config)
            with self._trace_context_factory():
                result = graph.invoke(state, config=config)
            return self.to_reply(result)
        except (SQLAlchemyError, OSError) as exc:
            logger.error(
                "Pattern database or storage operation failed: %s; SQLSTATE=%s",
                type(exc).__name__,
                _safe_sqlstate(exc),
            )
            raise StorageUnavailable() from exc
        except GroqAPIError as exc:
            logger.error("Groq request failed: %s", type(exc).__name__)
            raise PatternFailure("llm") from exc
        except PATTERN_ERRORS as exc:
            logger.error("Pattern processing failed: %s", type(exc).__name__)
            raise PatternFailure("pattern") from exc


def last_message_text(result: dict[str, Any]) -> str:
    """Texto del último mensaje del agente; el patrón debe terminar con una respuesta."""
    messages = result.get("messages", [])
    if messages and isinstance(messages[-1], AIMessage):
        content = messages[-1].content
        if isinstance(content, str) and content.strip():
            return content
    if messages and isinstance(messages[-1].content, str):
        return messages[-1].content
    raise ValueError("El patrón no produjo una respuesta de chat.")


def _safe_sqlstate(exc: BaseException) -> str:
    """Solo el código SQLSTATE de PostgreSQL (cinco caracteres), nunca el mensaje."""
    origin = getattr(exc, "orig", None)
    sqlstate = getattr(origin, "sqlstate", None) or getattr(origin, "pgcode", None)
    if isinstance(sqlstate, str) and re.fullmatch(r"[0-9A-Z]{5}", sqlstate):
        return sqlstate
    return "unavailable"
