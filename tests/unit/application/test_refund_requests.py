from decimal import Decimal

import pytest

from app.application.refunds import request_refund
from app.domain.refunds import RefundEligibilityError


class RefundRepository:
    def __init__(self):
        self.calls = []

    def request_refund(self, **kwargs):
        self.calls.append(kwargs)
        return {"id": 12, "ticket_id": 34}


def test_refund_request_normalizes_money_and_only_registers_requested_intent():
    repository = RefundRepository()

    result = request_refund(
        repository,
        customer_id=2,
        payment_id=8,
        amount="12.5",
        reason="  Producto   defectuoso ",
    )

    assert result.status == "REQUESTED"
    assert result.amount == Decimal("12.50")
    assert repository.calls == [{
        "customer_id": 2,
        "payment_id": 8,
        "amount": Decimal("12.50"),
        "reason": "Producto defectuoso",
    }]


@pytest.mark.parametrize("amount,reason", [("0", "motivo"), ("-2", "motivo"), ("4", " ")])
def test_refund_request_rejects_invalid_input_before_database_write(amount, reason):
    repository = RefundRepository()

    with pytest.raises(RefundEligibilityError):
        request_refund(repository, customer_id=2, payment_id=8, amount=amount, reason=reason)

    assert repository.calls == []
