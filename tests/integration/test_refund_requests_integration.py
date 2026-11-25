from decimal import Decimal

import pytest

from app.application.refunds import request_refund
from app.database.repository import ServiceRepository
from app.domain.refunds import RefundEligibilityError


class _Result:
    def __init__(self, row=None, scalar=None):
        self.row, self.scalar = row, scalar

    def mappings(self):
        return self

    def first(self):
        return self.row

    def one(self):
        return self.row

    def scalar_one(self):
        return self.scalar


class _Session:
    def __init__(self, results):
        self.results = iter(results)
        self.statements = []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def begin(self):
        return self

    def execute(self, statement, params):
        self.statements.append((str(statement), params))
        return next(self.results)


def test_refund_use_case_registers_request_and_never_moves_money():
    session = _Session([
        _Result(row={"id": 9, "ticket_id": 4, "amount": Decimal("100"), "status": "COMPLETED"}),
        _Result(row=None),
        _Result(scalar=Decimal("20")),
        _Result(row={"id": 12, "payment_id": 9, "ticket_id": 4, "amount": Decimal("30"), "status": "REQUESTED"}),
    ])
    repository = ServiceRepository(session_factory=lambda: session)

    request = request_refund(
        repository,
        customer_id=3,
        payment_id=9,
        amount="30.00",
        reason="Producto defectuoso",
    )

    sql = " ".join(statement for statement, _ in session.statements).upper()
    assert request.status == "REQUESTED"
    assert request.amount == Decimal("30.00")
    assert "FOR UPDATE" in sql
    assert "INSERT INTO REFUNDS" in sql
    assert "UPDATE PAYMENTS" not in sql
    assert "UPDATE TICKETS" not in sql


def test_refund_use_case_rejects_ineligible_payment_without_refund_insert():
    session = _Session([
        _Result(row={"id": 9, "ticket_id": 4, "amount": Decimal("100"), "status": "PENDING"}),
    ])
    repository = ServiceRepository(session_factory=lambda: session)

    with pytest.raises(RefundEligibilityError):
        request_refund(
            repository,
            customer_id=3,
            payment_id=9,
            amount="30.00",
            reason="Producto defectuoso",
        )

    assert len(session.statements) == 1
    assert all("INSERT INTO refunds" not in statement for statement, _ in session.statements)
