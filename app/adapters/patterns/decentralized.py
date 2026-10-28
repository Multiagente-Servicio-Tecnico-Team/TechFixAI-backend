"""Adaptador del patrón Red descentralizada (`app/agents/decentralized`).

En `develop` sus herramientas son simuladas: no propone presupuestos, por eso
los botones aceptar/rechazar no aplican (`supports_quotes = False`).
"""
from typing import Any

from langchain_core.messages import HumanMessage

from app.adapters.patterns.base import GraphPattern, last_message_text
from app.domain.chat import PatternReply


class DecentralizedPattern(GraphPattern):
    id = "decentralized"
    name = "Red descentralizada"
    supports_quotes = False

    def build_graph(self) -> Any:
        from langgraph.checkpoint.memory import MemorySaver

        from app.agents.decentralized.graph import build_graph

        return build_graph(checkpointer=MemorySaver())

    def initial_state(self, customer_id: int, message: HumanMessage) -> dict[str, Any]:
        # La red todavía no recibe la identidad del cliente.
        return {"messages": [message]}

    def prepare(self, graph: Any, state: dict[str, Any], config: dict[str, Any]) -> None:
        """Cada turno empieza con el control de transferencias reiniciado."""
        previous = graph.get_state(config).values
        state.update(
            turn_start_index=len(previous.get("messages", [])),
            handoff_count=0,
            handoff_history=[],
            tool_iterations={},
            errors=[],
            next_agent=None,
        )

    def to_reply(self, result: dict[str, Any]) -> PatternReply:
        return PatternReply(reply=last_message_text(result))
