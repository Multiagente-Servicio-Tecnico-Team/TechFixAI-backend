from decimal import Decimal

from app.domain.money import to_money
from app.domain.refunds import RefundEligibilityError, RefundRequest


def request_refund(
    repository,
    *,
    customer_id: int,
    payment_id: int,
    amount: Decimal | str | int,
    reason: str,
) -> RefundRequest:
    refund_amount = to_money(amount)
    clean_reason = " ".join(reason.split())
    if customer_id <= 0 or payment_id <= 0:
        raise RefundEligibilityError("La referencia de pago no es válida.")
    if refund_amount <= 0:
        raise RefundEligibilityError("El importe debe ser positivo.")
    if not clean_reason or len(clean_reason) > 1000:
        raise RefundEligibilityError("Indica un motivo de hasta 1000 caracteres.")
    try:
        row = repository.request_refund(
            customer_id=customer_id,
            payment_id=payment_id,
            amount=refund_amount,
            reason=clean_reason,
        )
    except ValueError as exc:
        raise RefundEligibilityError(str(exc)) from exc
    return RefundRequest(
        id=int(row["id"]),
        payment_id=payment_id,
        ticket_id=int(row["ticket_id"]) if row.get("ticket_id") is not None else None,
        amount=refund_amount,
    )
