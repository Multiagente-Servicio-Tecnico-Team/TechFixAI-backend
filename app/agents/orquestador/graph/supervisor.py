from uuid import uuid4

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from app.agents.orquestador.agentes.almacen import almacen_node
from app.agents.orquestador.agentes.atencion import atencion_node
from app.agents.orquestador.agentes.tecnico import tecnico_node
from app.agents.orquestador.agentes.ventas import persistencia_node, ventas_node
from app.agents.orquestador.graph.state import AgentState
from app.config import create_chat_model


def _supervisor_node(state: AgentState) -> dict[str, object]:
    return {}


def _supervisor_route(state: AgentState) -> str:
    if state.get("pc_build_pending"):
        return "pc_armados"
    if (state.get("warranty_status_pending") or state.get("warranty_claim_pending")
            or state.get("logistics_pending")):
        return "postventa"
    if state.get("ticket_lookup_pending"):
        return "consulta_ticket"
    if state.get("supplier_procurement_pending"):
        return "compras"
    if state.get("refund_request_pending"):
        return "reembolsos"
    if state.get("awaiting_clarification") or state.get("awaiting_ticket_confirmation"):
        return END
    if state.get("ticket_confirmed") and "ticket_id" not in state:
        return "persistencia"
    if "diagnosis" not in state:
        return "tecnico"
    if "inventory" not in state:
        return "almacen"
    if not state.get("quote_preview_ready"):
        return "ventas"
    return END


def build_graph():
    create_chat_model()
    builder = StateGraph(AgentState)
    builder.add_node("supervisor", _supervisor_node)
    def customer_ticket_node(state: AgentState) -> dict[str, object]:
        from app.application.tickets import lookup_customer_ticket
        from app.database.repository import ServiceRepository
        from langchain_core.messages import AIMessage

        customer_id = state.get("user_id")
        ticket = lookup_customer_ticket(
            ServiceRepository(), customer_id=customer_id, ticket_code=state.get("ticket_code", "")
        )
        if ticket is None:
            reply = "No encontré un ticket con ese código asociado a tu cuenta."
        else:
            reply = f"El ticket {ticket['code']} tiene estado {ticket['status']}."
        return {"ticket_lookup_pending": False, "response": reply, "messages": [AIMessage(content=reply)]}

    builder.add_node("consulta_ticket", customer_ticket_node)
    from app.agents.orquestador.agentes.postventa import postventa_node
    builder.add_node("postventa", postventa_node)
    from app.agents.orquestador.agentes.pc_build import pc_build_node
    builder.add_node("pc_armados", pc_build_node)
    builder.add_node("atencion", atencion_node)
    builder.add_node("tecnico", tecnico_node)
    builder.add_node("almacen", almacen_node)
    builder.add_node("ventas", ventas_node)
    builder.add_node("persistencia", persistencia_node)
    from app.agents.refund_requests import make_refund_agent
    from app.agents.orquestador.agentes.compras import procurement_node
    from app.database.repository import ServiceRepository
    builder.add_node("reembolsos", make_refund_agent(ServiceRepository()))
    builder.add_node("compras", procurement_node)
    builder.add_edge(START, "atencion")
    builder.add_edge("atencion", "supervisor")
    builder.add_conditional_edges("supervisor", _supervisor_route)
    builder.add_edge("tecnico", "supervisor")
    builder.add_edge("almacen", "supervisor")
    builder.add_edge("ventas", "supervisor")
    builder.add_edge("persistencia", "supervisor")
    builder.add_edge("reembolsos", END)
    builder.add_edge("compras", END)
    builder.add_edge("consulta_ticket", END)
    builder.add_edge("postventa", END)
    builder.add_edge("pc_armados", END)
    return builder.compile(checkpointer=MemorySaver())


def new_thread_id() -> str:
    return str(uuid4())
