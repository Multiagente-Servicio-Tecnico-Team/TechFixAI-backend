"""Agente de almacén del patrón Orquestador."""

from app.agents.orquestador.agentes.almacen import almacen_node


def warehouse_agent_node(state):
    return almacen_node(state)
