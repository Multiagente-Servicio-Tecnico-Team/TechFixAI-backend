from langgraph.graph import END

from app.agents.jerarquico.graph.state import ServiceState


def after_supervisor(state: ServiceState) -> str:
    if state.get("capabilities_response"):
        return END
    return {
        "service": "technical_team_supervisor",
        "informational": "faq_agent",
        "confirm": "warehouse_agent",
        "sale": "commercial_team_supervisor",
        "pc_build": "commercial_team_supervisor",
        "warranty_status": "operations_team_supervisor",
        "warranty_claim": "operations_team_supervisor",
        "refund_request": "refund_agent",
        "supplier_procurement": "purchasing_agent",
        "logistics": "operations_team_supervisor",
        "inventory_selection": "warehouse_agent",
        "diagnosis_only": "warehouse_agent",
        "awaiting_inventory_selection": END,
        "awaiting_build_selection": END,
        "awaiting_confirmation": END,
        "declined": END,
        "clarification": END,
        "customer_not_found": END,
    }.get(state.get("route", ""), END)


def after_operations_supervisor(state: ServiceState) -> str:
    if state.get("route") in {"warranty_status", "warranty_claim"}:
        return "warranty_agent"
    if state.get("route") == "logistics":
        return "logistics_agent"
    return END


def after_logistics(state: ServiceState) -> str:
    # Sales and PC_BUILD have no service ticket. A PC_BUILD warranty is
    # attached to its paid sales order inside payment confirmation.
    return END


def after_technical_supervisor(state: ServiceState) -> str:
    return "knowledge_retrieval"


def after_knowledge_retrieval(state: ServiceState) -> str:
    if state.get("request_type") == "SUPPORT":
        return "software_support_agent"
    return "technical_support_agent"


def after_inventory(state: ServiceState) -> str:
    if state.get("outcome") == "inventory_confirmed":
        return "sales_agent"
    if state.get("outcome") == "procurement_unavailable":
        return "purchasing_agent"
    return END


def after_sales(state: ServiceState) -> str:
    if state.get("route") == "confirm" and state.get("outcome") != "price_changed":
        return "billing_agent"
    return "quote_suggestion_response"
