"""Tickets del cliente con su último presupuesto (vista de solo lectura de «Mis Tickets»)."""
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from app.domain.money import to_money


@dataclass(frozen=True)
class TicketQuoteLine:
    name: str
    quantity: int
    unit_price: Decimal
    subtotal: Decimal

    def __post_init__(self) -> None:
        object.__setattr__(self, "quantity", int(self.quantity))
        object.__setattr__(self, "unit_price", to_money(self.unit_price))
        object.__setattr__(self, "subtotal", to_money(self.subtotal))


@dataclass(frozen=True)
class TicketQuote:
    status: str
    labor_cost: Decimal | None
    parts_cost: Decimal | None
    total_amount: Decimal | None
    created_at: datetime | str | None
    lines: tuple[TicketQuoteLine, ...] = ()

    def __post_init__(self) -> None:
        for name in ("labor_cost", "parts_cost", "total_amount"):
            value = getattr(self, name)
            object.__setattr__(self, name, None if value is None else to_money(value))
        object.__setattr__(self, "lines", tuple(self.lines))


@dataclass(frozen=True)
class CustomerTicket:
    code: str
    title: str
    failure_description: str
    request_type: str
    status: str
    created_at: datetime | str | None = None
    updated_at: datetime | str | None = None
    quote: TicketQuote | None = None
