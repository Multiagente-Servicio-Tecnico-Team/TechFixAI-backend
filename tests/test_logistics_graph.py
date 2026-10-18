"""Real compiled network and SQL repository with isolated SQLite fixtures."""
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4
import pytest
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from fastapi.testclient import TestClient
from app.accounts.config import Settings
from app.main import create_app, PATTERN_NAMES
from test_software_e2e import network, call, pairs
from test_logistics_repository import logistics_db, repair
from test_pending_payments import payment_db
from test_decentralized_repository import database


def state(db, text="Prefiero ingreso presencial"):
    return dict(messages=[HumanMessage(content=text)], current_agent="logistica",
        customer_id=1,ticket_id=db[5]["id"],request_revision=0)


def test_checkpoint_before_insert_then_idempotent_recovery(network, logistics_db, monkeypatch):
    db = logistics_db
    repair(db)
    saver = MemorySaver()
    graph = network[0].build_graph(checkpointer=saver,financial_repository=db[0])
    config = {"configurable":{"thread_id":"logistics-recovery"}}
    ctx = {"authenticated_customer_id":1}
    original = db[0].create_initial_logistics
    spy = MagicMock(wraps=original)
    monkeypatch.setattr(db[0], "create_initial_logistics", spy)
    graph.invoke(state(db), config, context=ctx,durability="sync")
    spy.assert_not_called()
    snapshot = graph.get_state(config)
    assert snapshot.next == ("ejecutar_logistica",)
    operation = snapshot.values["pending_logistics_operation"]
    # Simulate commit succeeded but response lost: retry must reuse the SQL row.
    committed = []
    def commit_then_fail(**kwargs):
        row = original(**kwargs)
        committed.append(row["id"])
        raise RuntimeError("Response interrupted")
    monkeypatch.setattr(db[0], "create_initial_logistics", commit_then_fail)
    with pytest.raises(RuntimeError):
        graph.invoke(None,config,context=ctx,durability="sync")
    assert graph.get_state(config).values["pending_logistics_operation"] == operation
    monkeypatch.setattr(db[0], "create_initial_logistics", original)
    rebuilt = network[0].build_graph(checkpointer=saver,financial_repository=db[0])
    result = rebuilt.invoke(None,config,context=ctx,durability="sync")
    assert result["logistics_record_id"] == committed[0]
    assert result["pending_logistics_operation"] is None
    assert result["logistics"]["status"] == "PENDING_RECEIPT"


@pytest.mark.parametrize("origin", ["soporte","tecnico","software","facturacion"])
def test_incoming_handoffs_and_audit(network, logistics_db, monkeypatch, origin):
    db = logistics_db
    repair(db)
    module, controls = network
    if origin == "facturacion":
        monkeypatch.setattr(module,"facturacion_node",lambda state, **kwargs: {
            "current_agent":"facturacion","messages":[call("transferir_a_logistica",motivo="Coordinar recepción") ]})
    else:
        controls["handlers"][origin] = lambda messages: call("transferir_a_logistica",motivo="Coordinar recepción")
    graph = module.build_graph(checkpointer=MemorySaver(),financial_repository=db[0])
    result = graph.invoke({**state(db,text="Consulta operativa"),"current_agent":origin},
        {"configurable":{"thread_id":"logistics-"+origin}},context={"authenticated_customer_id":1},durability="sync")
    assert result["current_agent"] == "logistica"
    assert result["handoff_history"][-1] == {"origin":origin,"destination":"logistica"}
    assert result["handoff_records"][-1]["reason"] == "Coordinar recepción"
    pairs(result)
    assert "garantia" in module.AGENT_NODES


def test_http_explicit_resume_and_other_client_rejected(network, logistics_db):
    db = logistics_db
    repair(db)
    # HTTP runs on another thread: clone the isolated fixture into StaticPool,
    # never connect a thread-local SQLite engine from an HTTP worker.
    from sqlalchemy import create_engine
    from sqlalchemy.pool import StaticPool
    from app.database.decentralized_repository import DecentralizedRepository
    engine = create_engine("sqlite://",connect_args={"check_same_thread":False},poolclass=StaticPool)
    source, target = db[1].raw_connection(), engine.raw_connection()
    try:
        source.driver_connection.backup(target.driver_connection)
    finally:
        source.close()
        target.close()
    repository = DecentralizedRepository(engine)
    graph = network[0].build_graph(checkpointer=MemorySaver(),financial_repository=repository)
    thread = "logistics-http-" + uuid4().hex
    config={"configurable":{"thread_id":thread}}
    graph.update_state(config,state(db))
    class Guard:
        settings = Settings(database_url=None,auth_secret="s"*48,secure_cookie=False)
        def require_customer(self,request):
            return SimpleNamespace(id=2 if request.headers.get("x-other") else 1)
    owners=MagicMock()
    def authorize(**kwargs):
        from app.database.conversation_owners import ConversationNotFound
        if kwargs["authenticated_customer_id"] != 1: raise ConversationNotFound()
        return {"thread_id":thread}
    owners.authorize.side_effect=authorize
    app=create_app(session_guard=Guard(),financial_repository=repository,
        graph_factories={name:lambda:graph for name in PATTERN_NAMES},conversation_owners_repository=owners,
        conversation_locks=SimpleNamespace(hold=lambda thread:nullcontext()),trace_context_factory=nullcontext)
    with TestClient(app) as client:
        body=dict(pattern="decentralized",conversation_id="conversation",message="Prefiero ingreso presencial")
        assert client.post("/api/chat",json=body).status_code == 200
        assert graph.get_state(config).next == ("ejecutar_logistica",)
        resume=dict(pattern="decentralized",conversation_id="conversation",action="resume_logistics")
        assert client.post("/api/chat",json=resume,headers={"x-other":"1"}).status_code == 404
        assert client.post("/api/chat",json=resume).status_code == 200
        assert graph.get_state(config).values["logistics"]["status"] == "PENDING_RECEIPT"
        assert client.post("/api/chat",json=resume).status_code == 409
    engine.dispose()


def test_real_financial_node_routes_only_persisted_payment(network, logistics_db):
    db=logistics_db
    payment=db[0].create_pending_payment(customer_id=1,ticket_id=db[5]["id"],quote_id=db[6]["id"],payment_code="PAY-LOG-FLOW")
    graph=network[0].build_graph(checkpointer=MemorySaver(),financial_repository=db[0])
    result=graph.invoke({**state(db,text="Consulta operativa"),"current_agent":"facturacion",
        "quote_id":db[6]["id"],"payment_id":payment["id"]},
        {"configurable":{"thread_id":"payment-to-logistics"}},context={"authenticated_customer_id":1},durability="sync")
    assert result["current_agent"] == "logistica"
    assert result["handoff_history"] == [{"origin":"facturacion","destination":"logistica"}]
    assert result["payment_id"] == payment["id"]
    assert "logistics_record_id" not in result
