from decimal import Decimal
from typing import Annotated, Any, Literal, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


class ServiceState(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]
    trace_id: str
    customer_email: str
    customer_id: int
    actor_user_id: int
    route: Literal[
        "service",
        "confirm",
        "declined",
        "awaiting_confirmation",
        "clarification",
        "informational",
        "customer_not_found",
        "sale",
        "pc_build",
        "warranty_status",
        "warranty_claim",
        "refund_request",
        "logistics",
        "inventory_selection",
        "diagnosis_only",
        "awaiting_inventory_selection",
        "awaiting_build_selection",
        "out_of_scope",
    ]
    team: Literal["commercial", "technical", "operations"]
    request_type: str
    diagnosis_type: Literal["HARDWARE", "SOFTWARE", "HYBRID", "NONE"]
    quote_type: Literal["REPAIR", "DIRECT_SALE", "PC_BUILD"]
    labor_task_type: Literal["maintenance", "diagnosis"]
    title: str
    failure_description: str
    provisional_diagnosis: str
    rag_context: str
    required_parts: list[dict[str, Any]]
    pending_commercial_requests: list[dict[str, Any]]
    budget_max: Decimal | None
    intended_use: str
    build_profile_id: str
    selected_build_profile_id: str
    build_options: list[dict[str, Any]]
    awaiting_build_selection: bool
    build_compatibility_notes: str
    awaiting_build_budget: bool
    inventory_selection_replaces_category: str
    manual_selection_complete: bool
    manual_selection_error: str
    matched_parts: list[dict[str, Any]]
    inventory_substitutions: list[dict[str, Any]]
    inventory_options_message: str
    inventory_options: list[dict[str, Any]]
    rag_documents: list[dict[str, Any]]
    faq_context: str
    capabilities_response: bool
    warranty_code: str
    warranty_id: int | None
    warranty_status: str
    warranty_claim_code: str
    awaiting_logistics: bool
    # Ticket al que pertenece la preferencia de entrega pendiente.
    logistics_ticket_id: int | None
    logistics_mode: Literal["PHYSICAL_STORE", "COURIER_SHIPMENT"]
    logistics_record_id: int | None
    payment_id: int | None
    payment_code: str
    awaiting_refund_details: bool
    refund_id: int | None
    refund_status: str
    ticket_status: str
    awaiting_quote_confirmation: bool
    awaiting_inventory_selection: bool
    awaiting_catalog_refinement: bool
    catalog_refinement_request: dict[str, Any]
    quote_changed: bool
    ticket_id: int | None
    ticket_code: str
    quote_id: int | None
    quote: dict[str, Any] | None
    outcome: str
