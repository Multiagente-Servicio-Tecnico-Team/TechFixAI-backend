"""Isolated payment contracts and transactional repository regression."""
from decimal import Decimal
import pytest
from sqlalchemy import Table, MetaData, Column, Integer, String, Numeric, CheckConstraint, ForeignKey, select, func, event
from sqlalchemy.dialects import postgresql
from test_decentralized_repository import database, ticket, quote
from app.database.decentralized_repository import RetryConflict
from app.agents.decentralized.payment_operations import (
    prepare_pending_payment_operation as prepare, validate_pending_payment_operation as validate,
    generate_payment_code,
)
from app.agents.decentralized.state import invalidate_request


@pytest.fixture
def payment_db(database):
    repo, engine, tickets, _, quotes, _ = database
    metadata = MetaData()
    for name in ("users", "tickets", "quotes"):
        Table(name, metadata, autoload_with=engine)
    payments = Table("payments", metadata, Column("id", Integer, primary_key=True),
        Column("ticket_id", ForeignKey("tickets.id"), nullable=False), Column("quote_id", ForeignKey("quotes.id")),
        Column("customer_id", ForeignKey("users.id"), nullable=False), Column("payment_code", String(50), unique=True, nullable=False),
        Column("amount", Numeric(10,2)), Column("status", String), CheckConstraint("amount > 0"))
    payments.create(engine)
    row = ticket(repo)
    accepted = quote(repo, row["id"])
    return repo, engine, tickets, quotes, payments, row, accepted


def pay(db, **changes):
    repo, _, _, _, _, row, accepted = db
    return repo.create_pending_payment(**{**dict(customer_id=1, ticket_id=row["id"],
        quote_id=accepted["id"], payment_code="PAY-TEST"), **changes})


def test_pending_payment_and_exact_retry(payment_db):
    repo, engine, _, _, payments, row, _ = payment_db
    first = pay(payment_db)
    assert first["amount"] == Decimal("360.00") and first["status"] == "PENDING"
    assert pay(payment_db) == first
    assert repo.get_ticket(customer_id=1, ticket_id=row["id"])["status"] == "PAYMENT_PENDING"
    with pytest.raises(RetryConflict):
        pay(payment_db, payment_code="OTHER-THREAD")
    with engine.connect() as conn:
        assert conn.scalar(select(func.count()).select_from(payments)) == 1


@pytest.mark.parametrize("changes", [dict(customer_id=2), dict(customer_id=3), dict(customer_id=4), dict(quote_id=99)])
def test_payment_ownership_and_customer(payment_db, changes):
    with pytest.raises(LookupError):
        pay(payment_db, **changes)


@pytest.mark.parametrize("status", ["PENDING", "REJECTED", "EXPIRED"])
def test_sql_quote_must_be_accepted(payment_db, status):
    _, engine, _, quotes, _, _, accepted = payment_db
    with engine.begin() as conn:
        conn.execute(quotes.update().values(status=status))
    with pytest.raises(ValueError):
        pay(payment_db)


@pytest.mark.parametrize("amount", [Decimal("0"), Decimal("-1")])
def test_sql_amount_positive(payment_db, amount):
    _, engine, _, quotes, _, _, _ = payment_db
    with engine.begin() as conn:
        conn.execute(quotes.update().values(total_amount=amount))
    with pytest.raises(ValueError):
        pay(payment_db)


@pytest.mark.parametrize("statement_prefix", ["INSERT INTO payments", "UPDATE tickets"])
def test_failure_rolls_back_payment_and_ticket(payment_db, statement_prefix):
    repo, engine, _, _, payments, row, _ = payment_db
    def fail(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith(statement_prefix):
            raise RuntimeError("Injected failure")
    event.listen(engine, "before_cursor_execute", fail)
    try:
        with pytest.raises(RuntimeError):
            pay(payment_db)
    finally:
        event.remove(engine, "before_cursor_execute", fail)
    assert repo.get_ticket(customer_id=1, ticket_id=row["id"])["status"] == "QUOTED"
    with engine.connect() as conn:
        assert conn.scalar(select(func.count()).select_from(payments)) == 0


def test_retry_conflicting_amount_and_no_status_rewind(payment_db):
    _, engine, tickets, quotes, payments, _, _ = payment_db
    pay(payment_db)
    with engine.begin() as conn:
        conn.execute(payments.update().values(status="COMPLETED"))
        conn.execute(tickets.update().values(status="PAID"))
    assert pay(payment_db)["status"] == "COMPLETED"
    with engine.begin() as conn:
        conn.execute(quotes.update().values(total_amount=Decimal("400")))
    with pytest.raises(RetryConflict):
        pay(payment_db)


def test_lock_order_compiles_for_postgresql(payment_db):
    _, engine, *_ = payment_db
    sql = []
    def capture(conn, clause, multiparams, params, execution_options):
        if getattr(clause, "_for_update_arg", None) is not None:
            sql.append(str(clause.compile(dialect=postgresql.dialect())))
    event.listen(engine, "before_execute", capture)
    try:
        pay(payment_db)
    finally:
        event.remove(engine, "before_execute", capture)
    assert len(sql) == 3
    assert all("FOR UPDATE" in statement for statement in sql)
    assert all(name in statement for name, statement in zip(("users", "tickets", "quotes"), sql))


def test_zero_updated_rows_rolls_back_payment(payment_db):
    _, engine, _, _, payments, _, _ = payment_db
    def no_update(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("UPDATE tickets"):
            statement += " AND 1=0"
        return statement, parameters
    event.listen(engine, "before_cursor_execute", no_update, retval=True)
    try:
        with pytest.raises(RuntimeError, match="exactamente"):
            pay(payment_db)
    finally:
        event.remove(engine, "before_cursor_execute", no_update)
    with engine.connect() as conn:
        assert conn.scalar(select(func.count()).select_from(payments)) == 0


def test_code_collision_other_ticket_is_explicit_conflict(payment_db):
    repo, *_ = payment_db
    pay(payment_db)
    other = ticket(repo, code="TCK-OTHER")
    other_quote = quote(repo, other["id"])
    with pytest.raises(RetryConflict):
        repo.create_pending_payment(customer_id=1, ticket_id=other["id"], quote_id=other_quote["id"], payment_code="PAY-TEST")


def state():
    return dict(customer_id=1, ticket_id=1, quote_id=2, request_revision=0)


def test_payment_contract_stable_detached_and_not_confirmed():
    current = state()
    patch = prepare(current, authenticated_customer_id=1, payment_code=generate_payment_code())
    current.update(patch)
    retry = prepare(current, authenticated_customer_id=1)
    assert retry == patch and set(patch) == {"pending_payment_operation"}
    assert "amount" not in patch["pending_payment_operation"]["payload"]
    retry["pending_payment_operation"]["payload"]["quote_id"] = 100
    assert current["pending_payment_operation"]["payload"]["quote_id"] == 2
    with pytest.raises(RetryConflict):
        invalidate_request(current, new_request=True)


@pytest.mark.parametrize("change", [dict(quote_id=3), dict(request_revision=1), dict(customer_id=2), dict(payment_id=8)])
def test_payment_contract_conflicts(change):
    current = state()
    current.update(prepare(current, authenticated_customer_id=1, payment_code="PAY-TEST"))
    current.update(change)
    with pytest.raises(RetryConflict):
        prepare(current, authenticated_customer_id=1)


@pytest.mark.parametrize("change", [dict(ticket_id=True), dict(quote_id=None), dict(request_revision=True)])
def test_invalid_contract(change):
    with pytest.raises(ValueError):
        prepare({**state(), **change}, authenticated_customer_id=1, payment_code="PAY-TEST")


def test_payload_rejects_model_amount():
    pending = prepare(state(), authenticated_customer_id=1, payment_code="PAY-TEST")["pending_payment_operation"]
    pending["payload"]["amount"] = Decimal("1")
    with pytest.raises(ValueError):
        validate(pending, authenticated_customer_id=1, request_revision=0)
