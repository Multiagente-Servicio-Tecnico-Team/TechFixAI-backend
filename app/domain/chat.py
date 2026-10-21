"""Entidades de la conversación con los agentes: patrón, presupuesto, ticket y respuesta."""
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal

from app.domain.money import CURRENCY, to_money

PatternId = Literal["hierarchical", "orchestrator", "decentralized"]
QuoteStatus = Literal["proposed", "saved", "confirmed", "rejected"]
QuoteAction = Literal["accept_quote", "reject_quote"]

# Texto que recibe el patrón cuando el cliente pulsa un botón de la tarjeta de presupuesto.
ACTION_MESSAGES: dict[str, str] = {
    "accept_quote": "Sí, confirmo",
    "reject_quote": "No, rechazo el presupuesto",
}


@dataclass(frozen=True)
class QuoteLine:
    label: str
    amount: Decimal

    def __post_init__(self) -> None:
        object.__setattr__(self, "amount", to_money(self.amount))


@dataclass(frozen=True)
class Quote:
    status: QuoteStatus
    lines: tuple[QuoteLine, ...]
    total: Decimal
    currency: str = CURRENCY

    def __post_init__(self) -> None:
        object.__setattr__(self, "lines", tuple(self.lines))
        object.__setattr__(self, "total", to_money(self.total))

    @property
    def is_pending(self) -> bool:
        return self.status == "proposed"


@dataclass(frozen=True)
class TicketRef:
    code: str
    status: str  # valores de ticket_status_enum del esquema de base de datos


@dataclass(frozen=True)
class PatternReply:
    """Resultado común de un turno, sea cual sea el patrón que lo produjo."""

    reply: str
    quote: Quote | None = None
    ticket: TicketRef | None = None
    # True cuando el patrón espera que el cliente acepte o rechace un presupuesto.
    pending_quote: bool = field(default=False)


def message_for_action(action: str | None, message: str | None) -> str:
    """El botón de la tarjeta se traduce a un mensaje que entiende el patrón."""
    if action:
        return ACTION_MESSAGES[action]
    return message or ""
