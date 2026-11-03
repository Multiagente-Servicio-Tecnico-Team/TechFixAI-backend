"""Reglas canónicas para gestión administrativa de tickets."""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

REQUEST_TYPES = frozenset({"REPAIR", "SALE", "PC_BUILD", "SUPPORT", "WARRANTY_CLAIM"})
TICKET_STATUSES = frozenset({"NEW", "IN_DIAGNOSIS", "QUOTED", "PAYMENT_PENDING", "PAID", "IN_REPAIR", "READY_FOR_DELIVERY", "DELIVERED", "CANCELLED", "WARRANTY_IN_REVIEW"})
ADVANCE_METHODS = frozenset({"YAPE_PLIN", "CASH", "CARD"})


def money(value: object | None) -> Decimal | None:
    if value is None:
        return None
    try:
        result = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("El importe debe ser un decimal válido.") from exc
    if not result.is_finite() or result <= 0 or result > Decimal("99999999.99"):
        raise ValueError("El importe debe ser mayor que cero y tener hasta 10 dígitos.")
    return result
