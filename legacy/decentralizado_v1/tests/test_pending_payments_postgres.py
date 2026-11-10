"""Opt-in real transactions; tables must be provisioned separately from SQL v2.

Requires PAYMENT_POSTGRES_INTEGRATION=1 and PAYMENT_TEST_DSN pointing to the
dedicated langgraph_payments_test database (never checkpoint/business database).
Creates only synthetic users/tickets/quotes/payments, cleans exact fixture IDs.
No DDL, migrations, setup(), agents or external services.
"""
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import logging
import os
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, make_url, MetaData, Table, select, func, event
from app.database.decentralized_repository import DecentralizedRepository, RetryConflict


pytestmark = pytest.mark.skipif(os.getenv("PAYMENT_POSTGRES_INTEGRATION") != "1",
                                reason="Explicit authorization for financial fixture writes required")


@pytest.fixture
def real_payment_fixture():
    dsn = os.getenv("PAYMENT_TEST_DSN")
    if not dsn:
        pytest.fail("Missing isolated payment test DSN", pytrace=False)
    url = make_url(dsn)
    if url.database != "langgraph_payments_test" or url.get_backend_name() != "postgresql":
        pytest.fail("Unexpected payment test target", pytrace=False)
    previous_logging = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    engine = create_engine(url.set(drivername="postgresql+psycopg"), pool_size=4,
                           connect_args={"connect_timeout": 10, "options": "-csearch_path=public"})
    marker = uuid4().hex
    tables = {}
    ids = {}
    try:
        with engine.connect() as conn:
            assert conn.exec_driver_sql("SELECT current_database()").scalar_one() == "langgraph_payments_test"
            metadata = MetaData()
            # Reflection must succeed for all tables before the first write.
            for name in ("users", "tickets", "quotes", "payments"):
                tables[name] = Table(name, metadata, schema="public", autoload_with=conn)
        with engine.begin() as conn:
            for key in ("customer", "other"):
                ids[key] = conn.execute(tables["users"].insert().values(
                    email=f"payment-{key}-{marker}@example.test", phone="000000000",
                    password_hash="NON_LOGIN_SYNTHETIC_TEST_HASH", name="Synthetic payment fixture",
                    role="CUSTOMER", active=True).returning(tables["users"].c.id)).scalar_one()
            ids["ticket"] = conn.execute(tables["tickets"].insert().values(
                code="TST-" + marker[:16], customer_id=ids["customer"], title="Synthetic payment test",
                failure_description="Synthetic service fixture, no executed service",
                request_type="SUPPORT", status="QUOTED", diagnosis_type="NONE",
                is_remote_service=False).returning(tables["tickets"].c.id)).scalar_one()
            ids["quote"] = conn.execute(tables["quotes"].insert().values(
                ticket_id=ids["ticket"], quote_type="REPAIR", labor_cost=Decimal("1.00"),
                parts_cost=Decimal("0.00"), total_amount=Decimal("1.00"), status="ACCEPTED",
                observations="Synthetic test amount; not a business tariff"
            ).returning(tables["quotes"].c.id)).scalar_one()
        yield DecentralizedRepository(engine), engine, tables, ids, "PAY-TST-" + marker
    finally:
        try:
            if tables and ids:
                with engine.begin() as conn:
                    if "ticket" in ids:
                        conn.execute(tables["payments"].delete().where(tables["payments"].c.ticket_id == ids["ticket"]))
                    if "quote" in ids:
                        conn.execute(tables["quotes"].delete().where(tables["quotes"].c.id == ids["quote"]))
                    if "ticket" in ids:
                        conn.execute(tables["tickets"].delete().where(tables["tickets"].c.id == ids["ticket"]))
                    for key in ("customer", "other"):
                        if key in ids:
                            conn.execute(tables["users"].delete().where(tables["users"].c.id == ids[key]))
        finally:
            engine.dispose()
            logging.disable(previous_logging)


def arguments(fixture):
    _, _, _, ids, code = fixture
    return dict(customer_id=ids["customer"], ticket_id=ids["ticket"], quote_id=ids["quote"], payment_code=code)


def test_real_payment_atomic_retry_and_ownership(real_payment_fixture):
    repo, engine, tables, ids, _ = real_payment_fixture
    args = arguments(real_payment_fixture)
    with pytest.raises(LookupError):
        repo.create_pending_payment(**{**args, "customer_id": ids["other"]})
    first = repo.create_pending_payment(**args)
    assert first["status"] == "PENDING" and first["amount"] == Decimal("1.00")
    assert repo.create_pending_payment(**args)["id"] == first["id"]
    with pytest.raises(RetryConflict):
        repo.create_pending_payment(**{**args, "payment_code": args["payment_code"] + "-other"})
    assert repo.get_ticket(customer_id=ids["customer"], ticket_id=ids["ticket"])["status"] == "PAYMENT_PENDING"
    with engine.connect() as conn:
        assert conn.scalar(select(func.count()).select_from(tables["payments"]).where(tables["payments"].c.quote_id == ids["quote"])) == 1


def test_real_payment_rollback(real_payment_fixture):
    repo, engine, tables, ids, _ = real_payment_fixture
    def fail(conn, clause, multiparams, params, execution_options):
        if getattr(getattr(clause, "table", None), "name", None) == "tickets" and getattr(clause, "is_update", False):
            raise RuntimeError("Injected update failure")
    event.listen(engine, "before_execute", fail)
    try:
        with pytest.raises(RuntimeError, match="Injected"):
            repo.create_pending_payment(**arguments(real_payment_fixture))
    finally:
        event.remove(engine, "before_execute", fail)
    with engine.connect() as conn:
        assert conn.scalar(select(func.count()).select_from(tables["payments"]).where(tables["payments"].c.ticket_id == ids["ticket"])) == 0
    assert repo.get_ticket(customer_id=ids["customer"], ticket_id=ids["ticket"])["status"] == "QUOTED"


@pytest.mark.parametrize("same_code", [True, False])
def test_real_concurrent_payment_transactions(real_payment_fixture, same_code):
    repo, engine, tables, ids, _ = real_payment_fixture
    barrier = Barrier(2)
    args = arguments(real_payment_fixture)
    def run(index):
        barrier.wait(timeout=10)
        code = args["payment_code"] if same_code else args["payment_code"] + str(index)
        try:
            return repo.create_pending_payment(**{**args, "payment_code": code})["id"]
        except RetryConflict:
            return "conflict"
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(run, index) for index in range(2)]
        results = [future.result(timeout=30) for future in futures]
    if same_code:
        assert results[0] == results[1] and results[0] != "conflict"
    else:
        assert results.count("conflict") == 1
    with engine.connect() as conn:
        assert conn.scalar(select(func.count()).select_from(tables["payments"]).where(tables["payments"].c.quote_id == ids["quote"])) == 1
