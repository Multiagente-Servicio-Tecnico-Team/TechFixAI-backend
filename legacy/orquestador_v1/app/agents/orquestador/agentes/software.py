"""Agente especialista de soporte de software del patrón Orquestador."""

from app.agents.orquestador.agentes.tecnico import technical_support_node
from app.agents.orquestador.graph.state import AgentState


def software_support_node(state: AgentState) -> dict[str, object]:
    return technical_support_node(state, mode="software")
