"""Nodo de rechazo de consultas fuera del dominio (patrón Jerárquico)."""
from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage

from app.agents.domain_guard import latest_human_text, out_of_scope_reply
from app.agents.jerarquico.graph.state import ServiceState


def make_out_of_scope_agent(llm: Any):
    def out_of_scope_agent(state: ServiceState) -> dict[str, Any]:
        reply = out_of_scope_reply(llm, latest_human_text(state["messages"]))
        return {
            "route": "out_of_scope",
            "outcome": "out_of_scope",
            "messages": [AIMessage(content=reply)],
        }

    return out_of_scope_agent
