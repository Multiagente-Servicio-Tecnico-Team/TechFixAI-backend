"""Reglas comunes de estados y stock para la capacidad comercial."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum


class CustomerOrigin(StrEnum):
    MANUAL = "MANUAL"
    PORTAL = "PORTAL"


class QuoteKind(StrEnum):
    REPAIR = "REPAIR"
    DIRECT_SALE = "DIRECT_SALE"
    PC_BUILD = "PC_BUILD"


class QuoteState(StrEnum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


class PaymentState(StrEnum):
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    REFUNDED = "REFUNDED"
    PARTIALLY_REFUNDED = "PARTIALLY_REFUNDED"


class ReservationState(StrEnum):
    RESERVED = "RESERVED"
    RELEASED = "RELEASED"
    CONSUMED = "CONSUMED"


class SalesOrderState(StrEnum):
    PAID = "PAID"
    PREPARING = "PREPARING"
    FULFILLED = "FULFILLED"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True)
class QuoteLine:
    spare_part_id: int
    name_snapshot: str
    code_snapshot: str | None
    quantity: int
    unit_price: Decimal
    subtotal: Decimal


@dataclass(frozen=True)
class InventoryReservation:
    quote_id: int
    customer_id: int
    state: ReservationState
    expires_at: datetime
    lines: tuple[QuoteLine, ...]


def available_stock(current_stock: int, active_reserved: int) -> int:
    """Return unreserved units; reject invalid persisted balances rather than hide them."""
    if isinstance(current_stock, bool) or isinstance(active_reserved, bool):
        raise ValueError("Los saldos de inventario deben ser enteros.")
    if current_stock < 0 or active_reserved < 0:
        raise ValueError("Los saldos de inventario no pueden ser negativos.")
    if active_reserved > current_stock:
        raise ValueError("Las reservas activas superan el stock físico.")
    return current_stock - active_reserved


def validate_sale_quote_expiry(expires_at: datetime, *, now: datetime) -> None:
    if expires_at.tzinfo is None or now.tzinfo is None:
        raise ValueError("Las fechas de vencimiento deben incluir zona horaria.")
    if expires_at <= now:
        raise ValueError("La cotización debe vencer en una fecha futura.")
