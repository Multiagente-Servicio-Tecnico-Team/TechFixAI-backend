"""Real graph, tools and SQL adapter; no PostgreSQL or LLM services."""
import pytest
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.messages import HumanMessage
from test_software_e2e import network, call, pairs
from test_garantia import warranty_db
from test_decentralized_repository import database


def test_claim_checkpoint_recovery_and_logistics_handoff(network,warranty_db,monkeypatch):
    module,_=network
    db=warranty_db
    saver=MemorySaver()
    graph=module.build_graph(checkpointer=saver,financial_repository=db[0])
    config={"configurable":{"thread_id":"warranty-recovery"}}
    ctx={"authenticated_customer_id":1}
    state=dict(messages=[HumanMessage(content="Reclamo")],current_agent="garantia",customer_id=1,
        ticket_id=db[5]["id"],request_revision=0,intent="WARRANTY_CLAIM",intake={"warranty_code":"WAR-TEST"})
    graph.invoke(state,config,context=ctx,durability="sync")
    snap=graph.get_state(config)
    assert snap.next == ("ejecutar_garantia",)
    operation=snap.values["pending_warranty_operation"]
    original=db[0].create_warranty_claim
    saved=[]
    def fail(**args):
        saved.append(original(**args)["id"])
        raise RuntimeError("Response lost")
    monkeypatch.setattr(db[0],"create_warranty_claim",fail)
    with pytest.raises(RuntimeError):
        graph.invoke(None,config,context=ctx,durability="sync")
    assert graph.get_state(config).values["pending_warranty_operation"] == operation
    monkeypatch.setattr(db[0],"create_warranty_claim",original)
    rebuilt=module.build_graph(checkpointer=saver,financial_repository=db[0])
    result=rebuilt.invoke(None,config,context=ctx,durability="sync")
    assert result["warranty_claim_id"] == saved[0]
    assert result["pending_warranty_operation"] is None
    assert result["current_agent"] == "logistica"
    assert result["handoff_history"][-1] == {"origin":"garantia","destination":"logistica"}
    pairs(result)


def test_support_to_warranty_query_no_operation(network,warranty_db):
    module,controls=network
    controls["handlers"]["soporte"]=lambda messages:call("transferir_a_garantia",motivo="Consultar vigencia")
    graph=module.build_graph(checkpointer=MemorySaver(),financial_repository=warranty_db[0])
    result=graph.invoke(dict(messages=[HumanMessage(content="Código: WAR-TEST")],customer_id=1,
        intent="WARRANTY_STATUS_CHECK",request_revision=0),{"configurable":{"thread_id":"warranty-query"}},
        context={"authenticated_customer_id":1},durability="sync")
    assert result["current_agent"] == "garantia"
    assert "pending_warranty_operation" not in result
    assert "ticket_id" not in result
    assert len(module.AGENT_NODES) == 9
    pairs(result)


def test_http_claim_resume_owned_stable_and_no_early_write(network,warranty_db):
    from contextlib import nullcontext
    from types import SimpleNamespace
    from unittest.mock import MagicMock
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.pool import StaticPool
    from app.main import create_app, PATTERN_NAMES
    from app.accounts.config import Settings
    from app.database.conversation_owners import ConversationNotFound
    from app.database.decentralized_repository import DecentralizedRepository
    db=warranty_db
    engine=create_engine("sqlite://",connect_args={"check_same_thread":False},poolclass=StaticPool)
    source,target=db[1].raw_connection(),engine.raw_connection()
    try:
        source.driver_connection.backup(target.driver_connection)
    finally:
        source.close()
        target.close()
    repo=DecentralizedRepository(engine)
    spy=MagicMock(wraps=repo.create_warranty_claim)
    repo.create_warranty_claim=spy
    graph=network[0].build_graph(checkpointer=MemorySaver(),financial_repository=repo)
    config={"configurable":{"thread_id":"warranty-http"}}
    graph.update_state(config,dict(messages=[],current_agent="garantia",customer_id=1,ticket_id=db[5]["id"],
        request_revision=0,intent="WARRANTY_CLAIM",intake={"warranty_code":"WAR-TEST"}))
    class Guard:
        settings=Settings(database_url=None,auth_secret="s"*48,secure_cookie=False)
        def require_customer(self,request):
            return SimpleNamespace(id=2 if request.headers.get("x-other") else 1)
    owners=MagicMock()
    def authorize(**args):
        if args["authenticated_customer_id"] != 1:
            raise ConversationNotFound()
        return {"thread_id":"warranty-http"}
    owners.authorize.side_effect=authorize
    app=create_app(session_guard=Guard(),financial_repository=repo,
        graph_factories={name:lambda:graph for name in PATTERN_NAMES},conversation_owners_repository=owners,
        conversation_locks=SimpleNamespace(hold=lambda thread:nullcontext()),trace_context_factory=nullcontext)
    try:
        with TestClient(app) as client:
            body=dict(pattern="decentralized",conversation_id="warranty-conversation",message="Reclamo")
            assert client.post("/api/chat",json=body).status_code == 200
            spy.assert_not_called()
            pending=graph.get_state(config).values["pending_warranty_operation"]
            assert client.post("/api/chat",json=body).status_code == 409
            resume=dict(pattern="decentralized",conversation_id="warranty-conversation",action="resume_warranty",customer_id=2,claim_code="ATTACK")
            assert client.post("/api/chat",json=resume,headers={"x-other":"1"}).status_code == 404
            assert graph.get_state(config).values["pending_warranty_operation"] == pending
            assert client.post("/api/chat",json=resume).status_code == 200
            spy.assert_called_once_with(**pending["payload"])
            assert graph.get_state(config).values["claim_code"] == pending["payload"]["claim_code"]
            assert client.post("/api/chat",json=resume).status_code == 409
    finally:
        engine.dispose()
