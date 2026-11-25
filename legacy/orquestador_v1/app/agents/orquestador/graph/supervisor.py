from uuid import uuid4

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from app.agents.orquestador.agentes.atencion import atencion_node
from app.agents.orquestador.agentes.billing import billing_agent_node
from app.agents.orquestador.agentes.faq import faq_node
from app.agents.orquestador.agentes.out_of_scope import out_of_scope_node
from app.agents.orquestador.agentes.logistics import logistics_node
from app.agents.orquestador.agentes.purchasing import purchasing_agent_node
from app.agents.orquestador.agentes.sales import sales_agent_node
from app.agents.orquestador.agentes.software import software_support_node
from app.agents.orquestador.agentes.tecnico import tecnico_node
from app.agents.orquestador.agentes.warehouse import warehouse_agent_node
from app.agents.orquestador.agentes.warranty import warranty_node
from app.agents.orquestador.graph.state import AgentState
from app.config import create_chat_model


def _supervisor_node(state: AgentState) -> dict[str, object]:
    return {}


def _supervisor_route(state: AgentState) -> str:
    if state.get("out_of_scope_pending"):
        return "out_of_scope_agent"
    if state.get("pc_build_pending"):
        return "sales_agent"
    if state.get("faq_pending"):
        return "faq_agent"
    if state.get("billing_pending"):
        return "billing_agent"
    if state.get("awaiting_sales_quote_confirmation") or state.get("sales_quote_status") in {
        "ACCEPTED", "REJECTED", "CANCELLED", "EXPIRED", "UNAVAILABLE",
    }:
        return END
    if state.get("warranty_status_pending") or state.get("warranty_claim_pending"):
        return "warranty_agent"
    if state.get("logistics_pending"):
        return "logistics_agent"
    if state.get("ticket_lookup_pending"):
        return "consulta_ticket"
    if state.get("supplier_procurement_pending"):
        return "purchasing_agent"
    if state.get("direct_sale_pending"):
        return "sales_agent"
    if state.get("refund_request_pending"):
        return "refund_agent"
    if state.get("awaiting_clarification") or state.get("awaiting_ticket_confirmation"):
        return END
    if state.get("ticket_confirmed"):
        return "billing_agent"
    if state.get("request_type") in {"REPAIR", "SUPPORT"} and not state.get("ticket_id"):
        return "crear_ticket"
    if (state.get("ticket_id") and state.get("diagnosis")
            and not state.get("diagnosis_persisted")):
        return "guardar_diagnostico"
    if "diagnosis" not in state:
        return (
            "software_support_agent"
            if state.get("request_type") == "SUPPORT"
            else "technical_support_agent"
        )
    if "inventory" not in state:
        return "warehouse_agent"
    if not state.get("quote_preview_ready"):
        return "sales_agent"
    return END


def _after_sales_agent(state: AgentState) -> str:
    if state.get("sales_agent_flow") in {"DIRECT_SALE", "PC_BUILD"}:
        return END
    return "supervisor"


def _after_billing_agent(state: AgentState) -> str:
    if state.get("billing_flow") == "SERVICE_QUOTE":
        return "supervisor"
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
    builder.add_node("logistics_agent", logistics_node)
    builder.add_node("warranty_agent", warranty_node)
    builder.add_node("faq_agent", faq_node)
    builder.add_node("out_of_scope_agent", out_of_scope_node)
    builder.add_node("atencion", atencion_node)
    builder.add_node("technical_support_agent", tecnico_node)
    builder.add_node("software_support_agent", software_support_node)
    builder.add_node("warehouse_agent", warehouse_agent_node)
    builder.add_node("sales_agent", sales_agent_node)
    builder.add_node("billing_agent", billing_agent_node)
    from app.agents.refund_requests import make_refund_agent
    from app.database.repository import ServiceRepository
    builder.add_node("refund_agent", make_refund_agent(ServiceRepository()))
    builder.add_node("purchasing_agent", purchasing_agent_node)
    builder.add_edge(START, "atencion")
    builder.add_edge("atencion", "supervisor")
    builder.add_conditional_edges("supervisor", _supervisor_route)
    builder.add_edge("technical_support_agent", "supervisor")
    builder.add_edge("software_support_agent", "supervisor")
    builder.add_edge("crear_ticket", "supervisor")
    builder.add_edge("guardar_diagnostico", "supervisor")
    builder.add_edge("warehouse_agent", "supervisor")
    builder.add_conditional_edges("sales_agent", _after_sales_agent)
    builder.add_conditional_edges("billing_agent", _after_billing_agent)
    builder.add_edge("refund_agent", END)
    builder.add_edge("purchasing_agent", END)
    builder.add_edge("consulta_ticket", END)
    builder.add_edge("logistics_agent", END)
    builder.add_edge("warranty_agent", END)
    builder.add_edge("faq_agent", END)
    builder.add_edge("out_of_scope_agent", END)
    return builder.compile(checkpointer=MemorySaver())


def new_thread_id() -> str:
    return str(uuid4())
