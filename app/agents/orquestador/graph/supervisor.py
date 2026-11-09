from uuid import uuid4

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from app.agents.orquestador.agentes.almacen import almacen_node
from app.agents.orquestador.agentes.atencion import atencion_node
from app.agents.orquestador.agentes.tecnico import tecnico_node
from app.agents.orquestador.agentes.ventas import persistencia_node, ventas_node
from app.agents.orquestador.agentes.direct_sales import direct_sales_node
from app.agents.orquestador.agentes.faq import faq_node
from app.agents.orquestador.graph.state import AgentState
from app.config import create_chat_model


def _supervisor_node(state: AgentState) -> dict[str, object]:
    return {}


def _supervisor_route(state: AgentState) -> str:
    if state.get("pc_build_pending"):
        return "pc_armados"
    if state.get("faq_pending"):
        return "faq"
    if state.get("awaiting_sales_quote_confirmation") or state.get("sales_quote_status") in {
        "ACCEPTED", "REJECTED", "CANCELLED", "EXPIRED", "UNAVAILABLE",
    }:
        return END
    if (state.get("warranty_status_pending") or state.get("warranty_claim_pending")
            or state.get("logistics_pending")):
        return "postventa"
    if state.get("ticket_lookup_pending"):
        return "consulta_ticket"
    if state.get("supplier_procurement_pending"):
        return "compras"
    if state.get("direct_sale_pending"):
        return "ventas_directas"
    if state.get("refund_request_pending"):
        return "reembolsos"
    if state.get("awaiting_clarification") or state.get("awaiting_ticket_confirmation"):
        return END
    if state.get("ticket_confirmed"):
        return "persistencia"
    if state.get("request_type") in {"REPAIR", "SUPPORT"} and not state.get("ticket_id"):
        return "crear_ticket"
    if (state.get("ticket_id") and state.get("diagnosis")
            and not state.get("diagnosis_persisted")):
        return "guardar_diagnostico"
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

    def create_service_ticket_node(state: AgentState) -> dict[str, object]:
        from app.database.repository import ServiceRepository

        customer_id = state.get("user_id")
        request_type = state.get("request_type")
        if type(customer_id) is not int or customer_id < 1:
            raise ValueError("Se requiere el cliente autenticado para crear el ticket.")
        if request_type not in {"REPAIR", "SUPPORT"}:
            raise ValueError("El tipo de ticket de servicio no es válido.")
        product = str(state.get("product", "")).strip()
        symptoms = str(state.get("symptoms", "")).strip()
        if not product or not symptoms:
            raise ValueError("El equipo y la descripción son obligatorios para crear el ticket.")
        ticket_code = state.get("ticket_code") or f"TCK-{uuid4().hex[:12].upper()}"
        ticket_id = ServiceRepository().create_intake_ticket(
            code=ticket_code,
            customer_id=customer_id,
            title=f"{product} - {state.get('category', 'Servicio técnico')}",
            failure_description=symptoms,
            request_type=request_type,
        )
        return {
            "ticket_id": ticket_id,
            "ticket_code": ticket_code,
            "ticket_status": "NEW",
            "diagnosis_persisted": False,
        }

    def persist_ticket_diagnosis_node(state: AgentState) -> dict[str, object]:
        from app.database.repository import ServiceRepository

        customer_id = state.get("user_id")
        ticket_id = state.get("ticket_id")
        if type(customer_id) is not int or type(ticket_id) is not int:
            raise ValueError("El ticket requiere la identidad autenticada del cliente.")
        diagnosis_type = state.get("diagnosis_type", "HARDWARE")
        ServiceRepository().update_ticket_diagnosis(
            ticket_id=ticket_id,
            customer_id=customer_id,
            diagnosis=str(state.get("diagnosis", "")),
            diagnosis_type=diagnosis_type,
        )
        return {"diagnosis_persisted": True, "ticket_status": "IN_DIAGNOSIS"}

    builder.add_node("crear_ticket", create_service_ticket_node)
    builder.add_node("guardar_diagnostico", persist_ticket_diagnosis_node)
    from app.agents.orquestador.agentes.postventa import postventa_node
    builder.add_node("postventa", postventa_node)
    from app.agents.orquestador.agentes.pc_build import pc_build_node
    builder.add_node("pc_armados", pc_build_node)
    builder.add_node("ventas_directas", direct_sales_node)
    builder.add_node("faq", faq_node)
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
    builder.add_edge("crear_ticket", "supervisor")
    builder.add_edge("guardar_diagnostico", "supervisor")
    builder.add_edge("almacen", "supervisor")
    builder.add_edge("ventas", "supervisor")
    builder.add_edge("persistencia", "supervisor")
    builder.add_edge("reembolsos", END)
    builder.add_edge("compras", END)
    builder.add_edge("consulta_ticket", END)
    builder.add_edge("postventa", END)
    builder.add_edge("pc_armados", END)
    builder.add_edge("ventas_directas", END)
    builder.add_edge("faq", END)
    return builder.compile(checkpointer=MemorySaver())


def new_thread_id() -> str:
    return str(uuid4())
