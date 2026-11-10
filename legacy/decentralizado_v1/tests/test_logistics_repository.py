"""SQL v2-shaped SQLite fixtures; no real PostgreSQL writes."""
from datetime import date
from decimal import Decimal
import pytest
from sqlalchemy import MetaData, Table, Column, Integer, String, Text, Date, DateTime, ForeignKey, select, func, event
from test_pending_payments import payment_db
from test_decentralized_repository import database
from app.database.decentralized_repository import RetryConflict


@pytest.fixture
def logistics_db(payment_db):
    repo, engine, tickets, quotes, payments, row, accepted = payment_db
    metadata = MetaData()
    for name in ("users", "tickets", "quotes"):
        Table(name, metadata, autoload_with=engine)
    logistics = Table("logistics_records", metadata, Column("id", Integer, primary_key=True),
        Column("ticket_id", ForeignKey("tickets.id"), nullable=False), Column("mode", String), Column("status", String),
        Column("courier_company", String(100)), Column("shipping_address", Text), Column("recipient_name", String(150)),
        Column("recipient_phone", String(20)), Column("tracking_number", String(100)), Column("scheduled_date", DateTime),
        Column("received_at", DateTime), Column("delivered_at", DateTime))
    warranties = Table("warranties", metadata, Column("id", Integer, primary_key=True),
        Column("customer_id", ForeignKey("users.id")), Column("start_date", Date), Column("end_date", Date), Column("status", String))
    claims = Table("warranty_claims", metadata, Column("id", Integer, primary_key=True),
        Column("warranty_id", ForeignKey("warranties.id")), Column("ticket_id", ForeignKey("tickets.id")), Column("status", String))
    metadata.create_all(engine)
    return repo, engine, tickets, quotes, payments, row, accepted, logistics, warranties, claims


def register(db, **changes):
    return db[0].create_initial_logistics(**{**dict(customer_id=1, ticket_id=db[5]["id"], mode="PHYSICAL_STORE"), **changes})


def repair(db):
    with db[1].begin() as conn:
        conn.execute(db[2].update().values(request_type="REPAIR", status="NEW"))


def test_repair_without_payment_and_retry(logistics_db):
    repair(logistics_db)
    first = register(logistics_db)
    assert first["status"] == "PENDING_RECEIPT"
    assert register(logistics_db)["id"] == first["id"]
    assert all(first[key] is None for key in ("tracking_number","scheduled_date","received_at","delivered_at"))
    assert logistics_db[0].get_ticket(customer_id=1, ticket_id=logistics_db[5]["id"])["status"] == "NEW"
    with pytest.raises(RetryConflict):
        register(logistics_db, mode="COURIER_SHIPMENT", courier_company="Otro")


@pytest.mark.parametrize("kind", ["SALE", "PC_BUILD"])
def test_sales_require_persisted_payment(logistics_db, kind):
    db = logistics_db
    with db[1].begin() as conn:
        conn.execute(db[2].update().values(request_type=kind))
    with pytest.raises(ValueError):
        register(db)
    db[0].create_pending_payment(customer_id=1,ticket_id=db[5]["id"],quote_id=db[6]["id"],payment_code="PAY-LOG-TEST")
    assert register(db)["status"] == "PENDING_RECEIPT"


@pytest.mark.parametrize("damage", ["wrong_customer", "failed", "wrong_amount", "rejected_quote"])
def test_payment_relationships_revalidated(logistics_db, damage):
    db = logistics_db
    db[0].create_pending_payment(customer_id=1,ticket_id=db[5]["id"],quote_id=db[6]["id"],payment_code="PAY-LOG-TEST")
    with db[1].begin() as conn:
        if damage == "wrong_customer": conn.execute(db[4].update().values(customer_id=2))
        if damage == "failed": conn.execute(db[4].update().values(status="FAILED"))
        if damage == "wrong_amount": conn.execute(db[4].update().values(amount=Decimal("1")))
        if damage == "rejected_quote": conn.execute(db[3].update().values(status="REJECTED"))
    with pytest.raises(ValueError):
        register(db)


def test_warranty_requires_real_claim_and_owner(logistics_db):
    db = logistics_db
    with db[1].begin() as conn:
        conn.execute(db[2].update().values(request_type="WARRANTY_CLAIM", status="WARRANTY_IN_REVIEW"))
    with pytest.raises(ValueError):
        register(db)
    with db[1].begin() as conn:
        database_date = conn.scalar(select(func.current_date()))
        if isinstance(database_date,str): database_date = date.fromisoformat(database_date)
        conn.execute(db[8].insert().values(id=1,customer_id=1,start_date=database_date,end_date=database_date,status="ACTIVE"))
        conn.execute(db[9].insert().values(warranty_id=1,ticket_id=db[5]["id"],status="IN_REVIEW"))
    assert register(db)["status"] == "PENDING_RECEIPT"


@pytest.mark.parametrize("changes", [dict(customer_id=2),dict(mode="INVALID"),dict(courier_company=True,mode="COURIER_SHIPMENT")])
def test_bad_owner_and_mode(logistics_db, changes):
    repair(logistics_db)
    with pytest.raises((ValueError, LookupError)):
        register(logistics_db, **changes)


def test_failure_rolls_back_and_courier_complete(logistics_db):
    db = logistics_db
    repair(db)
    def fail(conn,cursor,statement,params,context,executemany):
        if statement.startswith("INSERT INTO logistics_records"):
            raise RuntimeError("Injected")
    event.listen(db[1], "before_cursor_execute", fail)
    try:
        with pytest.raises(RuntimeError): register(db)
    finally:
        event.remove(db[1], "before_cursor_execute", fail)
    with db[1].connect() as conn:
        assert conn.scalar(select(func.count()).select_from(db[7])) == 0
    assert register(db, mode="COURIER_SHIPMENT",courier_company="Empresa de prueba")["shipping_address"] is None
