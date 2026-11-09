"""Puertos de la aplicación: lo que los casos de uso necesitan del exterior.

Cada patrón multiagente (Jerárquico, Orquestador, Red descentralizada) se consume
como un servicio que cumple `ChatPattern`; así el chat y las pruebas funcionan con
cualquiera de ellos y la comparación usa la misma entrada.
"""
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal, Protocol, runtime_checkable

from app.domain.chat import PatternReply
from app.domain.inventory import InventoryPart, InventoryPartDraft
from app.domain.tickets import CustomerTicket


CatalogMatchStatus = Literal["exact", "family_options", "ambiguous", "not_found"]
QuoteStatus = Literal["PENDING", "ACCEPTED", "REJECTED", "STALE"]
RefundStatus = Literal["REQUESTED", "APPROVED", "PROCESSED", "REJECTED"]
LogisticsMode = Literal["PHYSICAL_STORE", "COURIER_SHIPMENT"]


@dataclass(frozen=True)
class CustomerContext:
    """Authenticated execution context injected by the server, never by a tool call."""

    customer_id: int
    conversation_id: str
    pattern_id: str


@dataclass(frozen=True)
class CatalogItem:
    id: int
    code: str
    name: str
    category: str
    unit_price: Decimal
    current_stock: int
    active: bool


@dataclass(frozen=True)
class CatalogMatch:
    requested_name: str
    status: CatalogMatchStatus
    items: tuple[CatalogItem, ...] = ()


@dataclass(frozen=True)
class QuoteLineDraft:
    item_id: int
    quantity: int
    unit_price: Decimal
    subtotal: Decimal


@dataclass(frozen=True)
class QuoteDraft:
    ticket_id: int
    quote_type: Literal["REPAIR", "DIRECT_SALE", "PC_BUILD"]
    labor_task_type: Literal["maintenance", "diagnosis", "sale", "pc_build"]
    labor_cost: Decimal
    parts_cost: Decimal
    total_amount: Decimal
    currency: str
    lines: tuple[QuoteLineDraft, ...] = ()


@dataclass(frozen=True)
class QuoteRecord:
    id: int
    ticket_id: int
    status: QuoteStatus
    total_amount: Decimal


@dataclass(frozen=True)
class WarrantyRecord:
    id: int
    code: str
    customer_id: int
    status: str
    ticket_id: int | None = None


@dataclass(frozen=True)
class WarrantyClaimRecord:
    id: int
    warranty_id: int
    status: str
    ticket_id: int | None = None


@dataclass(frozen=True)
class LogisticsPreference:
    ticket_id: int
    customer_id: int
    mode: LogisticsMode
    record_id: int | None = None


@dataclass(frozen=True)
class RefundRequestDraft:
    payment_id: int
    customer_id: int
    amount: Decimal
    reason: str


@dataclass(frozen=True)
class RefundRequestRecord:
    id: int
    payment_id: int
    ticket_id: int
    amount: Decimal
    status: RefundStatus


@dataclass(frozen=True)
class KnowledgeFilters:
    areas: frozenset[str] = frozenset()
    trust_levels: frozenset[str] = frozenset()
    audience: str | None = None


@dataclass(frozen=True)
class RetrievedPassage:
    content: str
    source_id: str
    source_path: str
    section: str
    content_digest: str
    trust_level: str
    score: float
    match_type: Literal["semantic", "lexical", "lexical_code", "hybrid"]


@runtime_checkable
class ChatPattern(Protocol):
    """Un patrón LangGraph visto desde la aplicación."""

    id: str
    name: str
    # False si el patrón no propone presupuestos (los botones aceptar/rechazar no aplican).
    supports_quotes: bool

    def reply(self, conversation_id: str, customer_id: int, message: str) -> PatternReply:
        """Procesa un turno. La memoria de la conversación es responsabilidad del patrón."""
        ...


class CustomerTicketReader(Protocol):
    def list_for_customer(self, customer_id: int) -> list[CustomerTicket]:
        """Solo los tickets del cliente indicado, con su último presupuesto."""
        ...


class AdminTicketRepository(Protocol):
    """Persistencia necesaria para las operaciones administrativas de tickets."""

    def list_admin_tickets(self, **filters) -> dict[str, object]: ...
    def get_admin_ticket(self, ticket_id: int) -> dict[str, object] | None: ...
    def create_admin_ticket(self, *, values: dict[str, object], code: str, actor_id: int) -> int: ...
    def update_admin_ticket_audited(self, ticket_id: int, values: dict[str, object], actor_id: int) -> bool: ...
    def list_ticket_audit_events(self, ticket_id: int) -> list[dict[str, object]]: ...
    def create_admin_ticket_quote(self, **values) -> dict[str, object] | None: ...


class InventoryRepository(Protocol):
    """Persistencia del catálogo operativo de repuestos."""

    def list_parts(self) -> list[InventoryPart]: ...
    def list_categories(self) -> list[str]: ...
    def create_part(self, part: InventoryPartDraft, *, actor_id: int) -> InventoryPart: ...
    def update_part(self, code: str, part: InventoryPartDraft, *, actor_id: int) -> InventoryPart | None: ...
    def delete_part(self, code: str) -> bool: ...
    def record_opening_balance(self, *, part_id: int, count: int, actor_id: int, reason: str, idempotency_key, request_hash: str): ...
    def adjust_stock(self, *, part_id: int, count: int, actor_id: int, reason: str, idempotency_key,
                     request_hash: str, expected_stock: int | None = None): ...
    def list_movements(self, **filters) -> dict[str, object]: ...


class SupplierPurchaseRepository(Protocol):
    """Persistencia administrativa de proveedores, compras y recepciones."""

    def list_suppliers(self, **filters) -> dict[str, object]: ...
    def get_supplier(self, supplier_id: int) -> dict[str, object] | None: ...
    def create_supplier(self, values: dict[str, object], *, actor_id: int) -> dict[str, object]: ...
    def update_supplier(self, supplier_id: int, values: dict[str, object], *, actor_id: int) -> dict[str, object] | None: ...
    def create_purchase(self, *, actor_id: int, draft, values: dict[str, object]) -> dict[str, object]: ...
    def get_purchase(self, purchase_id: int) -> dict[str, object] | None: ...
    def list_purchases(self, **filters) -> dict[str, object]: ...
    def update_purchase(self, *, actor_id: int, purchase_id: int, values: dict[str, object]) -> dict[str, object] | None: ...
    def cancel_purchase(self, *, actor_id: int, purchase_id: int) -> dict[str, object] | None: ...
    def receive_purchase(self, *, actor_id: int, purchase_id: int, idempotency_key, request_hash: str, values: dict[str, object]) -> tuple[dict[str, object], bool]: ...
    def list_receipts(self, purchase_id: int) -> list[dict[str, object]] | None: ...


class CatalogReader(Protocol):
    def lookup_inventory(self, requested_name: str, quantity: int) -> dict[str, object]: ...

    def find_spare_parts(self, search_term: str) -> list[dict[str, object]]: ...

    def find_catalog_items(
        self, search_term: str, *, limit: int = 20
    ) -> list[dict[str, object]]: ...

    def find_spare_part_by_code(self, code: str) -> dict[str, object] | None: ...

    def find_spare_part_alternatives(
        self, search_term: str
    ) -> list[dict[str, object]]: ...


class QuoteWriter(Protocol):
    def create_quote(self, draft: QuoteDraft) -> QuoteRecord: ...

    def accept_quote(self, customer_id: int, quote_id: int) -> QuoteRecord: ...

    def reject_quote(self, customer_id: int, quote_id: int) -> QuoteRecord: ...


class AcceptedQuoteWriter(Protocol):
    def accept_ticket_quote(
        self,
        *,
        ticket_id: int,
        customer_id: int,
        quote_type: str,
        labor_cost: Decimal,
        parts_cost: Decimal,
        total_amount: Decimal,
        observations: str,
        parts: list[dict[str, object]],
        payment_code: str,
    ) -> dict[str, object]: ...


class WarrantyReader(Protocol):
    def find_owned_warranty(self, customer_id: int, warranty_code: str) -> WarrantyRecord | None: ...


class WarrantyClaimWriter(Protocol):
    def create_warranty_claim(
        self, customer_id: int, warranty_id: int, description: str
    ) -> WarrantyClaimRecord: ...


class LogisticsWriter(Protocol):
    def record_logistics_preference(
        self, customer_id: int, ticket_id: int, mode: LogisticsMode
    ) -> LogisticsPreference: ...


class RefundRequestWriter(Protocol):
    def request_refund(self, draft: RefundRequestDraft) -> RefundRequestRecord: ...


class KnowledgeRetriever(Protocol):
    def retrieve(
        self, query: str, *, filters: KnowledgeFilters, limit: int = 3
    ) -> list[RetrievedPassage]: ...


class AttemptLimiter(Protocol):
    """Límite de intentos por clave en una ventana de tiempo."""

    def blocked(self, key: str) -> bool: ...

    def fail(self, key: str) -> None: ...


@dataclass(frozen=True)
class TranscriptionResult:
    text: str


class AudioTranscriber(Protocol):
    """Transcribe audio bytes. Provider-specific SDK types stay in adapters."""

    def transcribe(self, audio: bytes, *, content_type: str) -> TranscriptionResult: ...


class AccountingRepository(Protocol):
    """Persistencia del libro contable; la identidad siempre viene de sesión."""

    def list_categories(self) -> list[dict[str, object]]: ...

    def create_entry(self, actor_id: int, idempotency_key, request_hash: str, draft): ...

    def list_entries(self, **filters) -> dict[str, object]: ...

    def get_entry(self, entry_id: int) -> dict[str, object] | None: ...

    def reverse_entry(self, actor_id: int, entry_id: int, operation_date, reason: str): ...
