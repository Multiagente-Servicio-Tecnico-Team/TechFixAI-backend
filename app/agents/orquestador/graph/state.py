from decimal import Decimal
from typing import Literal
from typing import Annotated, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field


class AgentState(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]
    user_id: object
    ticket_id: int
    ticket_code: str
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
    matched_parts: list[dict[str, object]]
    build_labor_cost: Decimal
    build_total: Decimal
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
    category: str = Field(description="Tipo de solicitud, redactado en español")
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
    labor_task_type: Literal["maintenance", "diagnosis"] = Field(
        description=(
            "diagnosis si la causa exacta no está identificada o requiere "
            "inspección; maintenance solo si el trabajo está determinado"
        )
    )
    parts: list[PartRequest] = Field(default_factory=list)
