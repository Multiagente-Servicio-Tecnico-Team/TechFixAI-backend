"""Deterministic validation and calculations for supplier purchase orders."""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
import hashlib
import json
from typing import Mapping


CENT = Decimal("0.01")
MAX_MONEY = Decimal("999999999999.99")
MAX_ORDER_QUANTITY = 999_999


class PurchaseOrderValidationFailure(ValueError):
    def __init__(self, detail: str, *, field: str | None = None):
        self.detail = detail
        self.field = field
        super().__init__(detail)


class PurchaseOrderConflictFailure(ValueError):
    """A requested lifecycle transition is incompatible with current state."""


@dataclass(frozen=True)
class PurchaseOrderLineDraft:
    spare_part_id: int | None
    description: str
    quantity: int
    unit_cost: Decimal
    subtotal: Decimal


@dataclass(frozen=True)
class PurchaseOrderDraft:
    supplier_id: int
    estimated_arrival: date | None
    notes: str | None
    items: tuple[PurchaseOrderLineDraft, ...]
    total_amount: Decimal


@dataclass(frozen=True)
class PurchaseOrderReceiptDraft:
    items: tuple[tuple[int, int], ...]
    notes: str | None
    request_hash: str


def validate_order_receipt(values: Mapping[str, object]) -> PurchaseOrderReceiptDraft:
    raw_items = values.get("items")
    if not isinstance(raw_items, (list, tuple)) or not raw_items or len(raw_items) > 100:
        raise PurchaseOrderValidationFailure("Agrega entre 1 y 100 líneas recibidas.", field="items")
    normalized: list[tuple[int, int]] = []
    seen: set[int] = set()
    for index, raw in enumerate(raw_items):
        prefix = f"items.{index}"
        if not isinstance(raw, Mapping):
            raise PurchaseOrderValidationFailure("La línea recibida no es válida.", field=prefix)
        line_id = raw.get("purchase_order_item_id")
        quantity = raw.get("quantity_received")
        if isinstance(line_id, bool) or not isinstance(line_id, int) or line_id < 1:
            raise PurchaseOrderValidationFailure("La línea de la orden no es válida.", field=f"{prefix}.purchase_order_item_id")
        if line_id in seen:
            raise PurchaseOrderValidationFailure("No repitas una línea en la recepción.", field=f"{prefix}.purchase_order_item_id")
        if isinstance(quantity, bool) or not isinstance(quantity, int) or not 1 <= quantity <= MAX_ORDER_QUANTITY:
            raise PurchaseOrderValidationFailure("La cantidad recibida debe ser un entero positivo.", field=f"{prefix}.quantity_received")
        normalized.append((line_id, quantity))
        seen.add(line_id)
    notes = values.get("notes")
    if notes is not None and not isinstance(notes, str):
        raise PurchaseOrderValidationFailure("Las notas deben ser texto.", field="notes")
    notes = notes.strip() or None if isinstance(notes, str) else None
    if notes and len(notes) > 2000:
        raise PurchaseOrderValidationFailure("Las notas admiten hasta 2000 caracteres.", field="notes")
    canonical = {"items": [{"purchase_order_item_id": line_id, "quantity_received": quantity}
                           for line_id, quantity in sorted(normalized)], "notes": notes}
    digest = hashlib.sha256(json.dumps(canonical, sort_keys=True, ensure_ascii=False,
                                      separators=(",", ":")).encode()).hexdigest()
    return PurchaseOrderReceiptDraft(tuple(normalized), notes, digest)


def validate_order_receipt_quantities(
    ordered: Mapping[int, int], received: Mapping[int, int], incoming: Mapping[int, int]
) -> dict[int, int]:
    if not incoming or set(incoming) - set(ordered):
        raise PurchaseOrderConflictFailure("Una o más líneas no pertenecen a esta orden.")
    updated = dict(received)
    for line_id, quantity in incoming.items():
        if quantity < 1 or updated.get(line_id, 0) + quantity > ordered[line_id]:
            raise PurchaseOrderConflictFailure("La cantidad recibida supera lo pendiente de la línea.")
        updated[line_id] = updated.get(line_id, 0) + quantity
    return updated


def next_order_receipt_status(current: str, ordered: Mapping[int, int], received: Mapping[int, int]) -> str:
    if current not in {"ISSUED", "PARTIALLY_RECEIVED"}:
        raise PurchaseOrderConflictFailure("La orden no admite nuevas recepciones.")
    if all(received.get(line_id, 0) >= quantity for line_id, quantity in ordered.items()):
        return "RECEIVED"
    return "PARTIALLY_RECEIVED"


def _money(value: object, field: str) -> Decimal:
    if not isinstance(value, (str, Decimal)):
        raise PurchaseOrderValidationFailure("El costo debe ser un importe decimal exacto.", field=field)
    try:
        amount = Decimal(value)
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise PurchaseOrderValidationFailure("El costo no es válido.", field=field) from exc
    if not amount.is_finite() or amount < 0 or amount.as_tuple().exponent < -2 or amount > MAX_MONEY:
        raise PurchaseOrderValidationFailure("El costo debe ser no negativo y tener hasta dos decimales.", field=field)
    return amount.quantize(CENT)


def validate_purchase_order(values: Mapping[str, object]) -> PurchaseOrderDraft:
    supplier_id = values.get("supplier_id")
    if isinstance(supplier_id, bool) or not isinstance(supplier_id, int) or supplier_id < 1:
        raise PurchaseOrderValidationFailure("Selecciona un proveedor válido.", field="supplier_id")

    raw_items = values.get("items")
    if not isinstance(raw_items, (list, tuple)) or not raw_items:
        raise PurchaseOrderValidationFailure("Agrega al menos una línea a la orden.", field="items")
    if len(raw_items) > 100:
        raise PurchaseOrderValidationFailure("La orden admite hasta 100 líneas.", field="items")

    lines: list[PurchaseOrderLineDraft] = []
    total = Decimal("0.00")
    for index, raw in enumerate(raw_items):
        prefix = f"items.{index}"
        if not isinstance(raw, Mapping):
            raise PurchaseOrderValidationFailure("La línea de la orden no es válida.", field=prefix)

        spare_part_id = raw.get("spare_part_id")
        if spare_part_id is not None and (
            isinstance(spare_part_id, bool) or not isinstance(spare_part_id, int) or spare_part_id < 1
        ):
            raise PurchaseOrderValidationFailure("El repuesto no es válido.", field=f"{prefix}.spare_part_id")

        description = raw.get("description")
        description = description.strip() if isinstance(description, str) else ""
        if not 1 <= len(description) <= 300:
            raise PurchaseOrderValidationFailure(
                "La descripción debe contener entre 1 y 300 caracteres.", field=f"{prefix}.description"
            )

        quantity = raw.get("quantity")
        if isinstance(quantity, bool) or not isinstance(quantity, int) or not 1 <= quantity <= MAX_ORDER_QUANTITY:
            raise PurchaseOrderValidationFailure(
                "La cantidad debe ser un entero positivo dentro del límite permitido.",
                field=f"{prefix}.quantity",
            )

        unit_cost = _money(raw.get("unit_cost"), f"{prefix}.unit_cost")
        subtotal = (Decimal(quantity) * unit_cost).quantize(CENT)
        if subtotal > MAX_MONEY:
            raise PurchaseOrderValidationFailure("El subtotal excede el máximo permitido.", field=prefix)
        total += subtotal
        if total > MAX_MONEY:
            raise PurchaseOrderValidationFailure("El total excede el máximo permitido.", field="items")
        lines.append(PurchaseOrderLineDraft(spare_part_id, description, quantity, unit_cost, subtotal))

    estimated_arrival = values.get("estimated_arrival")
    if estimated_arrival is not None and not isinstance(estimated_arrival, date):
        raise PurchaseOrderValidationFailure("La fecha estimada no es válida.", field="estimated_arrival")
    notes = values.get("notes")
    if notes is not None and not isinstance(notes, str):
        raise PurchaseOrderValidationFailure("Las notas deben ser texto.", field="notes")
    if isinstance(notes, str):
        notes = notes.strip() or None
        if notes and len(notes) > 2000:
            raise PurchaseOrderValidationFailure("Las notas admiten hasta 2000 caracteres.", field="notes")

    return PurchaseOrderDraft(supplier_id, estimated_arrival, notes, tuple(lines), total)


def transition_order_status(current: str, action: str, *, reason: str | None = None) -> str:
    """Validate and return the target status for an explicit ADMIN command."""
    if action == "ISSUE":
        if current != "DRAFT":
            raise PurchaseOrderConflictFailure("Solo se puede emitir una orden en borrador.")
        return "ISSUED"
    if action == "CANCEL":
        if current not in {"DRAFT", "ISSUED", "PARTIALLY_RECEIVED"}:
            raise PurchaseOrderConflictFailure("No se puede cancelar una orden recibida o ya cancelada.")
        if not isinstance(reason, str) or not 1 <= len(reason.strip()) <= 500:
            raise PurchaseOrderValidationFailure(
                "El motivo debe contener entre 1 y 500 caracteres.", field="reason"
            )
        return "CANCELLED"
    raise PurchaseOrderValidationFailure("La transición solicitada no es válida.", field="action")
