"""Agente par de fuera de dominio del patrón Descentralizado."""
from langchain_core.messages import AIMessage

from app.agents.decentralized.policy import latest_user_message
from app.agents.domain_guard import out_of_scope_reply
from app.config import create_chat_model


def out_of_scope_node(state):
    """Redacta una negativa cortés sin responder la consulta ajena y termina el turno."""
    reply = out_of_scope_reply(create_chat_model(), latest_user_message(state))
    return {
        "current_agent": "fuera_de_dominio",
        "outcome": "out_of_scope",
        "messages": [AIMessage(content=reply)],
    }
