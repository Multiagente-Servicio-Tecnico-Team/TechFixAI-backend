"""Warranty contracts and SQL adapter using isolated SQL-v2-shaped SQLite."""
from datetime import date, timedelta
from unittest.mock import MagicMock
import pytest
from sqlalchemy import MetaData, Table, Column, Integer, String, Text, Date, ForeignKey, event, select, func
from test_decentralized_repository import database, ticket, quote
from app.database.decentralized_repository import RetryConflict
from app.agents.decentralized.garantia import garantia_node
from app.agents.decentralized.warranty_operations import prepare_warranty_claim, validate_pending_warranty_operation
from app.agents.decentralized.tools.garantia_tools import transferir_a_garantia


@pytest.fixture
def warranty_db(database):
    repo, engine, tickets, parts, quotes, details = database
    metadata = MetaData()
    for name in ("users", "tickets", "quotes"):
        Table(name, metadata, autoload_with=engine)
    warranties = Table("warranties", metadata, Column("id", Integer, primary_key=True),
        Column("ticket_id", ForeignKey("tickets.id")), Column("quote_id", ForeignKey("quotes.id")),
        Column("customer_id", ForeignKey("users.id"), nullable=False), Column("warranty_code", String(50), unique=True, nullable=False),
        Column("item_or_service_name", String(200), nullable=False), Column("serial_number", String(100)),
        Column("warranty_months", Integer, nullable=False), Column("start_date", Date, nullable=False),
        Column("end_date", Date, nullable=False), Column("status", String, nullable=False), Column("terms_and_conditions", Text))
    claims = Table("warranty_claims", metadata, Column("id", Integer, primary_key=True),
        Column("warranty_id", ForeignKey("warranties.id"), nullable=False), Column("ticket_id", ForeignKey("tickets.id")),
        Column("claim_code", String(50), unique=True, nullable=False), Column("reason", Text, nullable=False),
        Column("status", String, nullable=False), Column("resolution_notes", Text))
    metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(warranties.insert().values(id=1, customer_id=1, warranty_code="WAR-TEST", item_or_service_name="SSD de prueba",
            warranty_months=3, start_date=date.today()-timedelta(days=1), end_date=date.today()+timedelta(days=30), status="ACTIVE"))
    row = ticket(repo, request_type="WARRANTY_CLAIM")
    return repo, engine, tickets, warranties, claims, row


def claim(db, **changes):
    return db[0].create_warranty_claim(**{**dict(customer_id=1, ticket_id=db[5]["id"], warranty_code="WAR-TEST", claim_code="CLM-TEST", reason="No enciende"), **changes})


@pytest.mark.parametrize("status,days,effective", [("ACTIVE",30,"ACTIVE"),("ACTIVE",-1,"EXPIRED"),("VOIDED",30,"VOIDED"),("CLAIMED",30,"CLAIMED")])
def test_query_dates_status_and_no_ticket_write(warranty_db, status, days, effective):
    repo, engine, tickets, warranties, *_ = warranty_db
    with engine.begin() as conn:
        conn.execute(warranties.update().values(status=status,end_date=date.today()+timedelta(days=days)))
    repo.create_ticket = MagicMock(side_effect=AssertionError("No query ticket writes"))
    result = garantia_node(dict(customer_id=1,intent="WARRANTY_STATUS_CHECK",intake={"warranty_code":"WAR-TEST"}),repository=repo,authenticated_customer_id=1)
    assert effective in result["messages"][0].content
    assert "pending_warranty_operation" not in result
    repo.create_ticket.assert_not_called()
    with pytest.raises(LookupError):
        repo.get_warranty(customer_id=2,warranty_code="WAR-TEST")


def test_claim_atomic_retry_conflict_and_owner(warranty_db):
    db = warranty_db
    first = claim(db)
    assert first["status"] == "IN_REVIEW"
    assert claim(db)["id"] == first["id"]
    assert db[0].get_ticket(customer_id=1,ticket_id=db[5]["id"])["status"] == "WARRANTY_IN_REVIEW"
    assert db[0].get_warranty_claim(customer_id=1,claim_id=first["id"])["id"] == first["id"]
    for changes in ({"claim_code":"CLM-OTHER"},{"reason":"Otro motivo"}):
        with pytest.raises(RetryConflict):
            claim(db,**changes)
    with pytest.raises(LookupError):
        claim(db,customer_id=2)
    with pytest.raises(LookupError):
        db[0].get_warranty_claim(customer_id=2,claim_id=first["id"])


@pytest.mark.parametrize("status,days", [("ACTIVE",-1),("VOIDED",30),("CLAIMED",30)])
def test_claim_not_valid(warranty_db,status,days):
    db=warranty_db
    with db[1].begin() as conn:
        conn.execute(db[3].update().values(status=status,end_date=date.today()+timedelta(days=days)))
    with pytest.raises(ValueError):
        claim(db)
    assert db[0].get_ticket(customer_id=1,ticket_id=db[5]["id"])["status"] == "NEW"


@pytest.mark.parametrize("statement", ["INSERT INTO warranty_claims","UPDATE tickets"])
def test_claim_rollback(warranty_db,statement):
    db=warranty_db
    def fail(conn,cursor,sql,parameters,context,executemany):
        if sql.startswith(statement):
            raise RuntimeError("Injected failure")
    event.listen(db[1],"before_cursor_execute",fail)
    with pytest.raises(RuntimeError):
        claim(db)
    event.remove(db[1],"before_cursor_execute",fail)
    with db[1].connect() as conn:
        assert conn.scalar(select(func.count()).select_from(db[4])) == 0
    assert db[0].get_ticket(customer_id=1,ticket_id=db[5]["id"])["status"] == "NEW"


def test_issue_authorization_three_months_and_retry(warranty_db):
    db=warranty_db
    row=ticket(db[0],code="TCK-SALE",request_type="SALE")
    accepted=quote(db[0],row["id"])
    args=dict(customer_id=1,ticket_id=row["id"],quote_id=accepted["id"],warranty_code="WAR-SALE",item_or_service_name="SSD de prueba")
    grant={key:args[key] for key in ("customer_id","ticket_id","quote_id","item_or_service_name")}
    with pytest.raises(ValueError):
        db[0].create_warranty(**args,authorization=None)
    result=db[0].create_warranty(**args,authorization=grant)
    assert result["warranty_months"] == 3 and result["status"] == "ACTIVE"
    with db[1].connect() as conn:
        today = conn.scalar(select(func.current_date()))
    assert result["start_date"] == today
    month=(today.month+2)%12+1
    assert result["end_date"].month == month
    assert db[0].create_warranty(**args,authorization=grant)["id"] == result["id"]
    with pytest.raises(RetryConflict):
        db[0].create_warranty(**{**args,"warranty_code":"WAR-OTHER"},authorization=grant)


def test_preparation_stable_and_conflicts(warranty_db):
    state=dict(customer_id=1,ticket_id=warranty_db[5]["id"],request_revision=0)
    operation=prepare_warranty_claim(state,authenticated_customer_id=1,warranty_code="WAR-TEST",reason="Falla")
    state["pending_warranty_operation"]=operation
    assert prepare_warranty_claim(state,authenticated_customer_id=1,warranty_code="WAR-TEST",reason="Falla") == operation
    for changes in ({"reason":"Otra"},{"warranty_code":"WAR-OTHER"}):
        with pytest.raises(RetryConflict):
            prepare_warranty_claim(state,authenticated_customer_id=1,**{**dict(warranty_code="WAR-TEST",reason="Falla"),**changes})
    with pytest.raises(RetryConflict):
        validate_pending_warranty_operation(operation,authenticated_customer_id=2,request_revision=0)
    with pytest.raises(RetryConflict):
        validate_pending_warranty_operation(operation,authenticated_customer_id=1,request_revision=1)
    assert "ticket_status" not in operation and "warranty_claim_id" not in operation


def test_node_prepares_without_write_and_no_fake_claim_return(warranty_db):
    db=warranty_db
    spy=MagicMock(wraps=db[0].create_warranty_claim)
    db[0].create_warranty_claim=spy
    state=dict(customer_id=1,ticket_id=db[5]["id"],request_revision=0,intent="WARRANTY_CLAIM",intake={"warranty_code":"WAR-TEST"})
    result=garantia_node(state,repository=db[0],authenticated_customer_id=1)
    assert result["warranty_preparation_ready"] is True
    assert not result["messages"][0].tool_calls
    spy.assert_not_called()
    result=garantia_node({**state,"warranty_claim_id":999},repository=db[0],authenticated_customer_id=1)
    assert not result["messages"][0].tool_calls


def test_handoff_reason_required():
    assert transferir_a_garantia.name == "transferir_a_garantia"
    with pytest.raises(ValueError):
        transferir_a_garantia.invoke({"motivo":" "})


def test_foreign_warranty_not_available_for_owned_claim(warranty_db):
    db=warranty_db
    with db[1].begin() as conn:
        conn.execute(db[3].update().values(customer_id=2))
    with pytest.raises(LookupError):
        claim(db)
    assert db[0].get_ticket(customer_id=1,ticket_id=db[5]["id"])["status"] == "NEW"


@pytest.mark.parametrize("revision", [None, True, -1, "0"])
def test_invalid_revision_cannot_prepare(warranty_db,revision):
    with pytest.raises(ValueError):
        prepare_warranty_claim(dict(customer_id=1,ticket_id=warranty_db[5]["id"],request_revision=revision),
            authenticated_customer_id=1,warranty_code="WAR-TEST",reason="Falla")


def test_pending_blocks_new_request_and_storage_errors_safe(warranty_db):
    from app.agents.decentralized.state import invalidate_request
    state=dict(customer_id=1,ticket_id=warranty_db[5]["id"],request_revision=0)
    state["pending_warranty_operation"]=prepare_warranty_claim(state,authenticated_customer_id=1,warranty_code="WAR-TEST",reason="Falla")
    with pytest.raises(RetryConflict):
        invalidate_request(state,new_request=True)
    repo=MagicMock()
    repo.get_warranty.side_effect=RuntimeError("SECRET DSN")
    result=garantia_node({**state,"intake":{"warranty_code":"WAR-TEST"}},repository=repo,authenticated_customer_id=1)
    assert "SECRET" not in result["messages"][0].content
    assert not result["warranty_preparation_ready"]
    repo.create_warranty_claim.assert_not_called()


def test_postgres_claim_row_locks(warranty_db):
    from sqlalchemy.dialects import postgresql
    statements=[]
    def capture(conn,clause,multiparams,params,execution_options):
        if getattr(clause,"_for_update_arg",None) is not None:
            statements.append(str(clause.compile(dialect=postgresql.dialect())))
    event.listen(warranty_db[1],"before_execute",capture)
    try:
        claim(warranty_db)
    finally:
        event.remove(warranty_db[1],"before_execute",capture)
    for name in ("users","tickets","warranties","warranty_claims"):
        assert any("FROM "+name in sql and "FOR UPDATE" in sql for sql in statements)
