"""Contratos compartidos: datos conversacionales separados del esquema PostgreSQL v2.

TypedDict describe datos, no valida entradas en ejecución. Los identificadores y
estados persistidos se incorporan sólo desde resultados confirmados de herramientas.
Los helpers devuelven actualizaciones; no ejecutan SQL ni detectan cambios de texto.
"""
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal
from typing_extensions import TypedDict
from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages
from app.agents.decentralized.handoffs import HandoffRecord


# Identidades lógicas; soporte/tecnico conservan Atención/Hardware existentes.
AgentName = Literal["soporte", "ventas", "tecnico", "software", "almacen",
                    "compras", "facturacion", "logistica", "garantia"]
ConversationIntent = Literal["REPAIR", "SUPPORT", "SALE", "PC_BUILD",
                             "WARRANTY_CLAIM", "WARRANTY_STATUS_CHECK",
                             "INFO_QUERY", "REFUND"]
# Valores exactos del DDL. INFO_QUERY, WARRANTY_STATUS_CHECK y REFUND no son enums SQL.
RequestType = Literal["REPAIR", "SALE", "PC_BUILD", "SUPPORT", "WARRANTY_CLAIM"]
DiagnosisType = Literal["HARDWARE", "SOFTWARE", "HYBRID", "NONE"]
TicketStatus = Literal["NEW", "IN_DIAGNOSIS", "QUOTED", "PAYMENT_PENDING", "PAID",
                       "IN_REPAIR", "READY_FOR_DELIVERY", "DELIVERED", "CANCELLED",
                       "WARRANTY_IN_REVIEW"]
QuoteType = Literal["REPAIR", "DIRECT_SALE", "PC_BUILD"]
QuoteStatus = Literal["PENDING", "ACCEPTED", "REJECTED", "EXPIRED"]
PaymentStatus = Literal["PENDING", "COMPLETED", "FAILED", "REFUNDED", "PARTIALLY_REFUNDED"]
PaymentMethod = Literal["CREDIT_CARD", "DEBIT_CARD", "BANK_TRANSFER", "CASH", "PAYMENT_GATEWAY"]
RefundStatus = Literal["REQUESTED", "APPROVED", "PROCESSED", "REJECTED"]
LogisticsMode = Literal["PHYSICAL_STORE", "COURIER_SHIPMENT"]
LogisticsStatus = Literal["PENDING_RECEIPT", "RECEIVED_AT_WORKSHOP", "READY_FOR_DISPATCH",
                          "IN_TRANSIT", "DELIVERED", "FAILED_DELIVERY"]
WarrantyStatus = Literal["ACTIVE", "EXPIRED", "VOIDED", "CLAIMED"]
WarrantyClaimStatus = Literal["IN_REVIEW", "APPROVED_REPAIR", "APPROVED_REPLACEMENT",
                              "APPROVED_REFUND", "REJECTED"]


class IntakeData(TypedDict, total=False):
    warranty_code: str
    product_description: str
    quantity: int
    title: str
    failure_description: str
    equipment: str
    brand: str
    model: str
    operating_system: str
    symptoms: list[str]
    budget: Decimal
    currency: str
    intended_use: str
    preferences: list[str]
    existing_components: list[str]
    missing_fields: list[str]


class Evidence(TypedDict):
    source: str
    content: str


class TechnicalAssessment(TypedDict, total=False):
    hardware_diagnosis: str
    software_diagnosis: str
    diagnosis_type: DiagnosisType
    estimated_labor_hours: Decimal
    is_remote_service: bool
    reported_facts: list[str]
    uncertainties: list[str]
    safe_steps: list[str]
    evidence: list[Evidence]
    compatibility_pending: list[str]
    backup_confirmed: bool
    destructive_action_authorized: bool


class PartRequest(TypedDict, total=False):
    name: str
    quantity: int
    code: str
    category: str
    specifications: list[str]
    optional: bool


class CatalogItem(TypedDict):
    id: int
    code: str
    name: str
    category: str | None
    description: str | None
    unit_price: Decimal
    current_stock: int


class InventoryCheck(TypedDict):
    # Estados de herramienta definidos por el prompt; no son enums SQL.
    status: Literal["AVAILABLE", "PARTIAL", "OUT_OF_STOCK", "NOT_FOUND", "NEEDS_DETAILS"]
    request: PartRequest
    candidates: list[CatalogItem]
    missing_quantity: int | None
    missing_fields: list[str]


class SupplierOffer(TypedDict, total=False):
    status: Literal["QUOTE_CONFIRMED", "ESTIMATE_ONLY", "PRICE_UNAVAILABLE", "UNAVAILABLE"]
    request: PartRequest
    supplier_id: int
    supplier_name: str
    unit_cost: Decimal
    currency: str
    delivery_lead_days: int
    lead_time_confirmed: bool
    valid_until: datetime
    source: str
    missing_fields: list[str]


class ProposalLine(TypedDict):
    spare_part_id: int | None
    custom_item_name: str | None
    quantity: int
    unit_price: Decimal
    subtotal: Decimal


class CommercialProposal(TypedDict):
    proposal_id: str
    customer_id: int
    ticket_id: int
    conversation_id: str
    request_type: RequestType
    inventory_snapshot: list[dict[str, Any]]
    request_revision: int
    quote_type: QuoteType
    currency: str
    labor_cost: Decimal
    parts_cost: Decimal
    total_amount: Decimal
    lines: list[ProposalLine]


class ProposalDecision(TypedDict):
    proposal_id: str
    request_revision: int
    accepted: bool
    # Debe venir de una decisión inequívoca, no de presupuesto/silencio/inferencia.
    explicit: bool


class PaymentData(TypedDict, total=False):
    amount: Decimal
    status: PaymentStatus
    payment_method: PaymentMethod | None
    transaction_reference: str | None


class RefundData(TypedDict, total=False):
    amount: Decimal
    reason: str
    status: RefundStatus


class LogisticsData(TypedDict, total=False):
    mode: LogisticsMode
    status: LogisticsStatus
    courier_company: str | None
    shipping_address: str | None
    recipient_name: str | None
    recipient_phone: str | None
    tracking_number: str | None
    scheduled_date: datetime | None
    received_at: datetime | None
    delivered_at: datetime | None


class WarrantyData(TypedDict, total=False):
    item_or_service_name: str
    serial_number: str | None
    warranty_months: int
    start_date: date
    end_date: date
    status: WarrantyStatus
    terms_and_conditions: str | None


class WarrantyClaimData(TypedDict, total=False):
    reason: str
    status: WarrantyClaimStatus
    resolution_notes: str | None
    resolved_at: datetime | None


class TicketCreationPayload(TypedDict):
    customer_id: int
    code: str
    title: str
    failure_description: str
    request_type: RequestType


class PendingTicketOperation(TypedDict):
    request_revision: int
    payload: TicketCreationPayload


class PaymentCreationPayload(TypedDict):
    customer_id: int
    ticket_id: int
    quote_id: int
    payment_code: str
    # Amount is read exclusively from the accepted SQL quote, never from an LLM.


class PendingPaymentOperation(TypedDict):
    request_revision: int
    payload: PaymentCreationPayload


class PendingQuoteOperation(TypedDict):
    proposal_id: str
    conversation_id: str
    request_revision: int
    payload: dict[str, Any]


class PendingLogisticsOperation(TypedDict):
    request_revision: int
    request_type: RequestType
    payload: dict[str, Any]


class WarrantyClaimCreationPayload(TypedDict):
    customer_id: int
    ticket_id: int
    warranty_code: str
    claim_code: str
    reason: str


class PendingWarrantyOperation(TypedDict):
    request_revision: int
    payload: WarrantyClaimCreationPayload


class AgentState(TypedDict, total=False):
    ticket_preparation_ready: bool
    # Historial compartido entre agentes
    messages: Annotated[list[AnyMessage], add_messages]

    # Inicio del turno actual, para no confundir herramientas de turnos anteriores.
    turn_start_index: int
    quote_scope: str
    quote: dict[str, Any]
    inventory_query: str | None

    # Agente actual y siguiente
    current_agent: str
    next_agent: str | None

    # Control de transferencias
    handoff_history: list[dict[str, Any]]
    # Registro estructurado interno; historial legacy conserva origen/destino.
    handoff_records: list[HandoffRecord]
    handoff_count: int

    # Control de herramientas
    tool_iterations: dict[str, int]

    # Repuestos identificados para la reparación
    required_parts: list[dict[str, Any]]

    # Indica si falta verificar el inventario
    inventory_pending: bool

    # Resultados obtenidos de PostgreSQL
    inventory_results: list[dict[str, Any]]

    # Errores registrados
    errors: list[str]

    # Campos opcionales nuevos: los cuatro agentes anteriores no deben rellenarlos.
    intent: ConversationIntent | None
    request_type: RequestType | None
    customer_id: int  # Exclusivamente desde la sesión autenticada.
    ticket_id: int | None
    ticket_code: str | None
    ticket_status: TicketStatus | None
    pending_ticket_operation: PendingTicketOperation | None
    ticket_correction_required: bool
    pending_payment_operation: PendingPaymentOperation | None
    pending_quote_operation: PendingQuoteOperation | None
    quote_receipt: dict[str, Any] | None
    pending_warranty_operation: PendingWarrantyOperation | None
    warranty_preparation_ready: bool
    pending_logistics_operation: PendingLogisticsOperation | None
    logistics_preparation_ready: bool
    quote_id: int | None
    quote_status: QuoteStatus | None
    payment_id: int | None
    payment_code: str | None
    refund_id: int | None
    logistics_record_id: int | None
    warranty_id: int | None
    warranty_code: str | None
    warranty_claim_id: int | None
    claim_code: str | None
    supplier_id: int | None
    purchase_order_id: int | None
    purchase_order_item_ids: list[int]

    intake: IntakeData
    technical_assessment: TechnicalAssessment
    requested_items: list[PartRequest]
    selected_items: list[CatalogItem]
    inventory_requested_by: AgentName | None
    inventory_checks: list[InventoryCheck]
    out_of_stock_items: list[PartRequest]
    supplier_offers: list[SupplierOffer]
    rag_evidence: list[Evidence]
    payment: PaymentData
    refund: RefundData
    logistics: LogisticsData
    warranty: WarrantyData
    warranty_claim: WarrantyClaimData

    # Versiones conversacionales, no columnas/estados PostgreSQL.
    request_revision: int
    inventory_revision: int | None
    proposal: CommercialProposal | None
    proposal_decision: ProposalDecision | None


def request_type_for_intent(intent: ConversationIntent) -> RequestType | None:
    """No fuerza una intención informativa o REFUND a un tipo persistible."""
    if intent in {"INFO_QUERY", "WARRANTY_STATUS_CHECK", "REFUND"}:
        return None
    if intent not in {"REPAIR", "SALE", "PC_BUILD", "SUPPORT", "WARRANTY_CLAIM"}:
        raise ValueError("Intención conversacional desconocida")
    return intent


def invalidate_request(state: AgentState, *, new_request: bool = False) -> AgentState:
    """Devuelve un patch al cambiar requisitos; el consumidor debe aplicarlo.

    Conserva identidad, historial y ticket en una revisión. Una solicitud nueva
    también desvincula el ticket y los datos de ingreso. No borra registros SQL.
    Cualquier resultado asíncrono debe comprobar request_revision antes de aplicarse.
    """
    if (state.get("pending_ticket_operation") is not None
            or state.get("pending_quote_operation") is not None
            or state.get("pending_payment_operation") is not None
            or state.get("pending_logistics_operation") is not None
            or state.get("pending_warranty_operation") is not None):
        from app.database.decentralized_repository import RetryConflict
        raise RetryConflict("Reconciliar operación pendiente antes de cambiar la solicitud")
    revision = state.get("request_revision", 0)
    if type(revision) is not int or revision < 0:
        raise ValueError("Versión de solicitud inválida")
    update: AgentState = {
        "request_revision": revision + 1,
        "ticket_correction_required": False,
        "ticket_preparation_ready": False,
        "inventory_revision": None, "proposal": None, "proposal_decision": None,
        "quote_receipt": None,
        "logistics_preparation_ready": False, "warranty_preparation_ready": False,
        "quote": {}, "quote_scope": "", "inventory_query": None,
        "required_parts": [], "inventory_results": [], "inventory_pending": True,
        "selected_items": [], "inventory_checks": [], "out_of_stock_items": [],
        "supplier_offers": [], "technical_assessment": {}, "rag_evidence": [],
        "inventory_requested_by": None, "next_agent": None,
        "quote_id": None, "quote_status": None, "payment_id": None,
        "payment_code": None, "refund_id": None, "logistics_record_id": None,
        "warranty_id": None, "warranty_code": None, "warranty_claim_id": None,
        "claim_code": None, "supplier_id": None, "purchase_order_id": None,
        "purchase_order_item_ids": [], "payment": {}, "refund": {},
        "logistics": {}, "warranty": {}, "warranty_claim": {},
        "handoff_count": 0, "handoff_history": [], "handoff_records": [], "tool_iterations": {}, "errors": [],
    }
    if new_request:
        update.update(ticket_id=None, ticket_code=None, ticket_status=None,
                      intent=None, request_type=None, intake={}, requested_items=[],
                      current_agent="soporte")
    return update


def proposal_is_accepted(state: AgentState) -> bool:
    """Aceptación explícita ligada a propuesta e inventario de la revisión vigente.

    No autoriza por sí sola escrituras ni certifica stock/compatibilidad/pago.
    """
    revision = state.get("request_revision")
    proposal = state.get("proposal")
    decision = state.get("proposal_decision")
    return (
        type(revision) is int and revision >= 0
        and type(state.get("inventory_revision")) is int
        and state["inventory_revision"] == revision
        and not state.get("inventory_pending", True)
        and isinstance(proposal, dict) and isinstance(decision, dict)
        and type(proposal.get("request_revision")) is int
        and proposal["request_revision"] == revision
        and type(decision.get("request_revision")) is int
        and decision["request_revision"] == revision
        and decision.get("accepted") is True and decision.get("explicit") is True
        and ("proposal_id" not in proposal or decision.get("proposal_id") == proposal["proposal_id"])
    )
