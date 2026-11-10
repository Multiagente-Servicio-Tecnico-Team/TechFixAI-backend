"""Nodo de rechazo de consultas fuera del dominio (patrón Orquestador)."""
from langchain_core.messages import AIMessage

from app.agents.domain_guard import latest_human_text, out_of_scope_reply
from app.config import create_chat_model


def out_of_scope_node(state: dict[str, object]) -> dict[str, object]:
    reply = out_of_scope_reply(create_chat_model(), latest_human_text(state.get("messages", [])))
    return {
        "out_of_scope_pending": False,
        "response": reply,
        "messages": [AIMessage(content=reply)],
    }
