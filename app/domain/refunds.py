from dataclasses import dataclass
from decimal import Decimal

from app.domain.errors import DomainError


@dataclass(frozen=True)
class RefundRequest:
    id: int
    payment_id: int
    ticket_id: int | None
    amount: Decimal
    status: str = "REQUESTED"


class RefundEligibilityError(DomainError, ValueError):
    """La solicitud no cumple las reglas de titularidad o saldo reembolsable."""

    code = "refund_ineligible"
    detail = "El pago no cumple los requisitos para registrar una solicitud de reembolso."

    def __init__(self, reason: str | None = None):
        super().__init__(reason or self.detail)
