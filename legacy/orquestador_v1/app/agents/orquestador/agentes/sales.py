"""Agente comercial único del Orquestador para servicio, venta y PC_BUILD."""

from app.agents.orquestador.agentes.direct_sales import direct_sales_node
from app.agents.orquestador.agentes.pc_build import pc_build_node
from app.agents.orquestador.agentes.ventas import ventas_node
from app.agents.orquestador.graph.state import AgentState


def sales_agent_node(state: AgentState) -> dict[str, object]:
    """Despacha subflujos comerciales sin añadir supervisores al grafo."""
    if state.get("pc_build_pending"):
        result = pc_build_node(state)
        return {**result, "sales_agent_flow": "PC_BUILD"}
    if state.get("direct_sale_pending"):
        result = direct_sales_node(state)
        return {**result, "sales_agent_flow": "DIRECT_SALE"}
    if state.get("request_type") in {"REPAIR", "SUPPORT"} and not state.get("quote_preview_ready"):
        result = ventas_node(state)
        return {**result, "sales_agent_flow": "SERVICE_QUOTE"}
    return {"sales_agent_flow": "SERVICE_QUOTE"}
