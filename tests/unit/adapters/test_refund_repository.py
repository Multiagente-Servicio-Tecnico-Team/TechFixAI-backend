from decimal import Decimal

import pytest

from app.database.repository import ServiceRepository


class Result:
    def __init__(self, row=None, scalar=None):
        self.row = row
        self.scalar = scalar

    def mappings(self):
        return self

    def first(self):
        return self.row

    def one(self):
        return self.row

    def scalar_one(self):
        return self.scalar


class Session:
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


def test_repository_registers_only_requested_status_under_payment_lock():
    session = Session([
        Result(row={"id": 9, "ticket_id": 4, "amount": Decimal("100"), "status": "COMPLETED"}),
        Result(row=None),
        Result(scalar=Decimal("20")),
        Result(row={"id": 12, "payment_id": 9, "ticket_id": 4, "amount": Decimal("30"), "status": "REQUESTED"}),
    ])
    repository = ServiceRepository(session_factory=lambda: session)

    result = repository.request_refund(
        customer_id=3, payment_id=9, amount=Decimal("30"), reason="Defecto"
    )

    assert result["status"] == "REQUESTED"
    assert "FOR UPDATE" in session.statements[0][0]
    assert "UPDATE payments" not in " ".join(sql for sql, _ in session.statements)
    assert session.statements[-1][1]["ticket_id"] == 4


@pytest.mark.parametrize(
    "payment,duplicate,expected",
    [
        (None, None, "No se encontró"),
        ({"id": 9, "ticket_id": 4, "amount": 100, "status": "PENDING"}, None, "completado"),
        ({"id": 9, "ticket_id": 4, "amount": 100, "status": "COMPLETED"}, {"id": 1}, "pendiente"),
    ],
)
def test_repository_rejects_ineligible_or_duplicate_refund(payment, duplicate, expected):
    session = Session([
        Result(row=payment),
        *([Result(row=duplicate)] if payment and payment["status"] == "COMPLETED" else []),
    ])
    repository = ServiceRepository(session_factory=lambda: session)

    with pytest.raises(ValueError, match=expected):
        repository.request_refund(
            customer_id=3, payment_id=9, amount=Decimal("30"), reason="Defecto"
        )

    assert not any("INSERT INTO refunds" in sql for sql, _ in session.statements)


def test_repository_rejects_amount_above_remaining_processed_balance():
    session = Session([
        Result(row={"id": 9, "ticket_id": 4, "amount": 100, "status": "COMPLETED"}),
        Result(row=None),
        Result(scalar=Decimal("80")),
    ])
    repository = ServiceRepository(session_factory=lambda: session)

    with pytest.raises(ValueError, match="saldo aún reembolsable"):
        repository.request_refund(
            customer_id=3, payment_id=9, amount=Decimal("30"), reason="Defecto"
        )
    assert len(session.statements) == 3


def test_payment_code_lookup_is_scoped_to_authenticated_customer():
    session = Session([Result(row={"id": 9})])
    repository = ServiceRepository(session_factory=lambda: session)

    assert repository.find_payment_id_by_code(3, "PAY-ABC123") == 9
    sql, params = session.statements[0]
    assert "payment_code = :payment_code" in sql
    assert "customer_id = :customer_id" in sql
    assert params == {"payment_code": "PAY-ABC123", "customer_id": 3}
