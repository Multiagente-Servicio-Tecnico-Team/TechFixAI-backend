"""Agente de compras a proveedores del patrón Orquestador."""

from app.agents.orquestador.agentes.compras import procurement_node


def purchasing_agent_node(state):
    return procurement_node(state)
