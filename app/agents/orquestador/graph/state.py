from decimal import Decimal
from typing import Literal
from typing import Annotated, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field


class AgentState(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]
    user_id: object
    faq_pending: bool
    faq_query: str
    faq_context: str
    request_type: Literal["REPAIR", "SUPPORT"]
    ticket_id: int
    ticket_code: str
    diagnosis_type: Literal["HARDWARE", "SOFTWARE", "HYBRID"]
    diagnosis_persisted: bool
    ticket_lookup_pending: bool
    warranty_code: str
    warranty_status_pending: bool
    warranty_claim_pending: bool
    logistics_pending: bool
    logistics_record_id: int
    logistics_mode: str
    warranty_claim_code: str
    warranty_id: int
    pc_build_pending: bool
    pc_build_collecting_use: bool
    pc_build_selected: bool
    awaiting_build_selection: bool
    build_intended_use: str
    build_budget_max: Decimal
    build_options: list[dict[str, object]]
    selected_build_profile_id: str
    selected_build_profile_name: str
    matched_parts: list[dict[str, object]]
    build_labor_cost: Decimal
    build_total: Decimal
    sales_quote_id: int
    sales_quote_status: str
    sales_quote_kind: str
    sales_payment_code: str
    awaiting_sales_quote_confirmation: bool
    direct_sale_pending: bool
    direct_sale_product: str
    direct_sale_quantity: int | None
    direct_sale_candidates: list[dict[str, object]]
    category: str
    product: str
    symptoms: str
    awaiting_clarification: bool
    clarification: str
    awaiting_ticket_confirmation: bool
    ticket_confirmed: bool
    diagnosis: str
    labor_cost: Decimal
    labor_task_type: Literal["maintenance", "diagnosis"]
    requested_parts: list[dict[str, object]]
    inventory: list[dict[str, object]]
    available_parts: list[dict[str, object]]
    parts_total: Decimal
    quote_id: int
    payment_code: str
    payment_status: str
    ticket_status: str
    quote_preview_ready: bool
    ticket_cancelled: bool
    total: Decimal
    response: str
    awaiting_refund_details: bool
    refund_request_pending: bool
    refund_id: int
    refund_status: str
    supplier_procurement_pending: bool
    outcome: str


class IntakeResult(BaseModel):
    intent: Literal["SERVICE", "FAQ"] = Field(
        default="SERVICE",
        description=(
            "FAQ para una pregunta informativa sobre datos y procesos descritos en la guía; "
            "SERVICE para diagnóstico, reparación o soporte de un equipo"
        ),
    )
    category: str = Field(description="Tipo de solicitud, redactado en español")
    request_type: Literal["REPAIR", "SUPPORT"] = Field(
        default="SUPPORT",
        description="REPAIR para reparación del equipo; SUPPORT para orientación o soporte técnico",
    )
    product: str = Field(description="Equipo, marca y modelo; texto en español excepto nombres propios")
    symptoms: str = Field(description="Síntomas descritos en español, breves y fieles al usuario")
    needs_clarification: bool = Field(
        description="True si falta información esencial para un diagnóstico inicial"
    )
    clarification_question: str = Field(
        description="Una pregunta concreta cuando hace falta aclarar; vacío en otro caso"
    )


class PartRequest(BaseModel):
    name: str = Field(description="Nombre específico del repuesto")
    quantity: int = Field(default=1, ge=1)


class TechnicalDiagnosis(BaseModel):
    diagnosis: str = Field(description="Diagnóstico técnico provisional y sus límites")
    diagnosis_type: Literal["HARDWARE", "SOFTWARE", "HYBRID"] = Field(
        default="HARDWARE",
        description="Clasificación de la causa provisional para registrar el ticket",
    )
    labor_task_type: Literal["maintenance", "diagnosis"] = Field(
        description=(
            "diagnosis si la causa exacta no está identificada o requiere "
            "inspección; maintenance solo si el trabajo está determinado"
        )
    )
    parts: list[PartRequest] = Field(default_factory=list)
