"""Reglas puras para compras a proveedores y recepción de inventario."""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Mapping


CENT = Decimal("0.01")
PAYMENT_METHODS = frozenset({"TRANSFER", "CASH", "CARD", "OTHER"})
PAYMENT_STATUSES = frozenset({"PENDING", "PAID"})
PURCHASE_STATUSES = frozenset({"REGISTERED", "PARTIALLY_RECEIVED", "RECEIVED", "CANCELLED"})


class PurchaseValidationFailure(ValueError):
    def __init__(self, detail: str, *, field: str | None = None):
        self.detail = detail
        self.field = field
        super().__init__(detail)


class PurchaseConflictFailure(ValueError):
    pass


def _money(value: object, field: str) -> Decimal:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise PurchaseValidationFailure("El importe no es válido.", field=field) from exc
    try:
        rounded = amount.quantize(CENT)
    except InvalidOperation as exc:
        raise PurchaseValidationFailure("El importe excede el máximo permitido.", field=field) from exc
    if not amount.is_finite() or amount < 0 or rounded != amount or amount > Decimal("999999999999.99"):
        raise PurchaseValidationFailure("El importe debe ser positivo o cero y tener hasta dos decimales.", field=field)
    return rounded


def _text(value: object, field: str, maximum: int, *, required: bool = True) -> str | None:
    if value is None and not required:
        return None
    clean = value.strip() if isinstance(value, str) else ""
    if not clean or len(clean) > maximum:
        raise PurchaseValidationFailure(f"El campo debe contener entre 1 y {maximum} caracteres.", field=field)
    return clean


@dataclass(frozen=True)
class ValidatedPurchaseLine:
    spare_part_id: int | None
    description: str
    quantity: Decimal
    unit_cost: Decimal
    discount_amount: Decimal
    tax_amount: Decimal
    line_total: Decimal


@dataclass(frozen=True)
class ValidatedPurchase:
    supplier_id: int
    purchase_order_id: int | None
    document_type: str
    document_series: str | None
    document_number: str
    issue_date: date
    due_date: date | None
    payment_method: str
    payment_status: str
    other_charges: Decimal
    notes: str | None
    lines: tuple[ValidatedPurchaseLine, ...]
    subtotal: Decimal
    tax_total: Decimal
    discount_total: Decimal
    total_amount: Decimal


def validate_supplier(values: Mapping[str, object], *, partial: bool = False) -> dict[str, object]:
    result: dict[str, object] = {}
    limits = {"name": 200, "tax_id": 20, "contact_name": 200, "contact_email": 255, "phone": 30}
    for field, max_length in limits.items():
        if field not in values and partial:
            continue
        value = values.get(field)
        if field == "name":
            result[field] = _text(value, field, max_length)
        elif value is None or (isinstance(value, str) and not value.strip()):
            result[field] = None
        else:
            clean = str(value).strip()
            if len(clean) > max_length:
                raise PurchaseValidationFailure("El valor excede la longitud permitida.", field=field)
            if field == "contact_email" and ("@" not in clean or "." not in clean.rsplit("@", 1)[-1]):
                raise PurchaseValidationFailure("El correo no tiene un formato válido.", field=field)
            result[field] = clean
    if "address" in values or not partial:
        address = values.get("address")
        result["address"] = address.strip() if isinstance(address, str) and address.strip() else None
    if "delivery_lead_days" in values or not partial:
        days = values.get("delivery_lead_days")
        if days is not None and (isinstance(days, bool) or not isinstance(days, int) or days < 0):
            raise PurchaseValidationFailure("El plazo debe ser un entero igual o mayor que cero.", field="delivery_lead_days")
        result["delivery_lead_days"] = days
    if "active" in values:
        if not isinstance(values["active"], bool):
            raise PurchaseValidationFailure("El estado activo debe ser booleano.", field="active")
        result["active"] = values["active"]
    return result


def validate_purchase(values: Mapping[str, object]) -> ValidatedPurchase:
    supplier_id = values.get("supplier_id")
    if isinstance(supplier_id, bool) or not isinstance(supplier_id, int) or supplier_id < 1:
        raise PurchaseValidationFailure("Selecciona un proveedor válido.", field="supplier_id")
    order_id = values.get("purchase_order_id")
    if order_id is not None and (isinstance(order_id, bool) or not isinstance(order_id, int) or order_id < 1):
        raise PurchaseValidationFailure("La orden de compra no es válida.", field="purchase_order_id")
    document_type = _text(values.get("document_type"), "document_type", 30)
    document_number = _text(values.get("document_number"), "document_number", 40)
    series = _text(values.get("document_series"), "document_series", 30, required=False)
    issue_date, due_date = values.get("issue_date"), values.get("due_date")
    if not isinstance(issue_date, date):
        raise PurchaseValidationFailure("La fecha de emisión no es válida.", field="issue_date")
    if due_date is not None and (not isinstance(due_date, date) or due_date < issue_date):
        raise PurchaseValidationFailure("El vencimiento debe ser igual o posterior a la emisión.", field="due_date")
    method, payment_status = values.get("payment_method"), values.get("payment_status")
    if method not in PAYMENT_METHODS:
        raise PurchaseValidationFailure("Selecciona un método de pago válido.", field="payment_method")
    if payment_status not in PAYMENT_STATUSES:
        raise PurchaseValidationFailure("El estado de pago no es válido.", field="payment_status")
    raw_items = values.get("items")
    if not isinstance(raw_items, (list, tuple)) or not raw_items:
        raise PurchaseValidationFailure("Agrega al menos una línea a la compra.", field="items")
    lines: list[ValidatedPurchaseLine] = []
    for index, raw in enumerate(raw_items):
        field_prefix = f"items.{index}"
        if not isinstance(raw, Mapping):
            raise PurchaseValidationFailure("La línea de compra no es válida.", field=field_prefix)
        spare_id = raw.get("spare_part_id")
        if spare_id is not None and (isinstance(spare_id, bool) or not isinstance(spare_id, int) or spare_id < 1):
            raise PurchaseValidationFailure("El repuesto no es válido.", field=f"{field_prefix}.spare_part_id")
        description = _text(raw.get("description"), f"{field_prefix}.description", 300)
        try:
            quantity = Decimal(str(raw.get("quantity")))
        except (InvalidOperation, ValueError, TypeError) as exc:
            raise PurchaseValidationFailure("La cantidad no es válida.", field=f"{field_prefix}.quantity") from exc
        if not quantity.is_finite() or quantity <= 0 or quantity.as_tuple().exponent < -3:
            raise PurchaseValidationFailure("La cantidad debe ser mayor que cero y admitir hasta tres decimales.", field=f"{field_prefix}.quantity")
        unit_cost = _money(raw.get("unit_cost"), f"{field_prefix}.unit_cost")
        discount = _money(raw.get("discount_amount", "0.00"), f"{field_prefix}.discount_amount")
        tax = _money(raw.get("tax_amount", "0.00"), f"{field_prefix}.tax_amount")
        gross = (quantity * unit_cost).quantize(CENT, rounding=ROUND_HALF_UP)
        gross = _money(gross, f"{field_prefix}.line_total")
        if discount > gross:
            raise PurchaseValidationFailure("El descuento no puede superar el importe bruto de la línea.", field=f"{field_prefix}.discount_amount")
        line_total = gross - discount + tax
        lines.append(ValidatedPurchaseLine(spare_id, description, quantity, unit_cost, discount, tax, line_total))
    subtotal = _money(sum(((line.quantity * line.unit_cost).quantize(CENT, rounding=ROUND_HALF_UP) for line in lines), Decimal("0.00")), "subtotal")
    discounts = _money(sum((line.discount_amount for line in lines), Decimal("0.00")), "discount_total")
    taxes = _money(sum((line.tax_amount for line in lines), Decimal("0.00")), "tax_total")
    charges = _money(values.get("other_charges", "0.00"), "other_charges")
    total = _money(subtotal - discounts + taxes + charges, "total_amount")
    return ValidatedPurchase(
        supplier_id, order_id, document_type, series, document_number, issue_date, due_date,
        str(method), str(payment_status), charges, values.get("notes") if isinstance(values.get("notes"), str) else None,
        tuple(lines), subtotal, taxes, discounts, total,
    )


def next_receipt_status(current: str, ordered: Mapping[int, Decimal], received_totals: Mapping[int, Decimal]) -> str:
    if current not in {"REGISTERED", "PARTIALLY_RECEIVED"}:
        raise PurchaseConflictFailure("La compra ya no admite recepciones.")
    if not ordered or any(qty <= 0 for qty in ordered.values()):
        raise PurchaseValidationFailure("Indica cantidades recibidas mayores que cero.", field="items")
    if any(item_id not in ordered or qty < 0 or qty > ordered[item_id] for item_id, qty in received_totals.items()):
        raise PurchaseConflictFailure("La cantidad recibida supera lo pendiente de la línea.")
    complete = all(received_totals.get(item_id, Decimal("0")) >= qty for item_id, qty in ordered.items())
    return "RECEIVED" if complete else "PARTIALLY_RECEIVED"
