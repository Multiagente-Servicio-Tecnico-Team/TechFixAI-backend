"""Actual repository with SQLite v2-shaped fixture and real graph. Not PostgreSQL certification."""
from unittest.mock import MagicMock
import pytest
from sqlalchemy import select, func
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
from test_decentralized_repository import database
from test_software_e2e import network, call, pairs
from test_session_guard import env, login, SETTINGS
import app.main as main


def initial(text):
    return dict(customer_id=1, request_revision=0, messages=[HumanMessage(content=text)])


@pytest.mark.parametrize("kind,text,destination", [
    ("REPAIR", "Mi laptop Lenovo se recalienta y funciona lentamente", "tecnico"),
    ("SUPPORT", "Solicitud: SUPPORT; Equipo: PC; Síntomas: falla el controlador", "software"),
    ("SALE", "Quiero comprar dos SSD 500GB SATA", "ventas"),
    ("PC_BUILD", "Quiero armar una PC; Uso: diseño; Presupuesto: 2500", "ventas"),
    ("WARRANTY_CLAIM", "Quiero reclamar mi garantía; Código: WAR-TEST; Motivo: se apaga", "garantia"),
])
def test_confirmed_ticket_precedes_handoff(network, database, kind, text, destination):
    module, controls = network
    repo, engine, tickets, *_ = database
    controls["handlers"]["tecnico"] = lambda messages: AIMessage(content="Orientación preliminar")
    controls["handlers"]["software"] = lambda messages: AIMessage(content="Orientación preliminar")
    saver = MemorySaver()
    original = repo.create_ticket
    operations = []
    def create(**payload):
        checkpoint = saver.get_tuple({"configurable": {"thread_id": kind}})
        assert checkpoint.checkpoint["channel_values"]["pending_ticket_operation"]["payload"] == payload
        assert not checkpoint.checkpoint["channel_values"].get("ticket_id")
        operations.append(payload)
        return original(**payload)
    repo.create_ticket = create
    graph = module.build_graph(checkpointer=saver, financial_repository=repo, ticket_writes=True)
    result = graph.invoke(initial(text), {"configurable": {"thread_id": kind}},
        context={"authenticated_customer_id": 1}, durability="sync")
    assert result["pending_ticket_operation"] and not result.get("ticket_id")
    assert operations == []
    result = graph.invoke(None, {"configurable": {"thread_id": kind}},
        context={"authenticated_customer_id": 1}, durability="sync")
    assert len(operations) == 1 and result["pending_ticket_operation"] is None
    row = repo.get_ticket(customer_id=1, ticket_id=result["ticket_id"])
    assert row["request_type"] == kind and row["status"] == "NEW"
    assert result["ticket_code"] == row["code"]
    assert result["handoff_history"][0] == {"origin": "soporte", "destination": destination}
    with engine.connect() as conn:
        assert conn.scalar(select(func.count()).select_from(tickets)) == 1
    pairs(result)


def test_retry_after_commit_and_lost_response_reuses_exact_operation(network, database):
    module, controls = network
    repo, engine, tickets, *_ = database
    controls["handlers"]["tecnico"] = lambda messages: AIMessage(content="Orientación preliminar")
    original = repo.create_ticket
    calls = []
    def lost_response(**payload):
        calls.append(payload)
        row = original(**payload)
        if len(calls) == 1:
            raise RuntimeError("Synthetic response loss after business commit")
        return row
    repo.create_ticket = lost_response
    saver = MemorySaver()
    config = {"configurable": {"thread_id": "lost-ticket"}}
    graph = module.build_graph(checkpointer=saver, financial_repository=repo, ticket_writes=True)
    graph.invoke(initial("Mi laptop no enciende"), config,
        context={"authenticated_customer_id": 1}, durability="sync")
    with pytest.raises(RuntimeError):
        graph.invoke(None, config, context={"authenticated_customer_id": 1}, durability="sync")
    pending = graph.get_state(config).values["pending_ticket_operation"]
    assert "ticket_id" not in graph.get_state(config).values
    restarted = module.build_graph(checkpointer=saver, financial_repository=repo, ticket_writes=True)
    recovered = restarted.invoke(None, config, context={"authenticated_customer_id": 1}, durability="sync")
    assert calls[0] == calls[1] == pending["payload"]
    assert recovered["pending_ticket_operation"] is None
    with engine.connect() as conn:
        assert conn.scalar(select(func.count()).select_from(tickets)) == 1
    pairs(recovered)


def test_faq_and_missing_specs_never_write(network, database):
    module, _ = network
    repo = database[0]
    repo.create_ticket = MagicMock(side_effect=AssertionError("Unexpected write"))
    graph = module.build_graph(checkpointer=MemorySaver(), financial_repository=repo, ticket_writes=True)
    for text in ("¿Qué servicios técnicos ofrecen?", "Quisiera comprar una SSD"):
        result = graph.invoke(initial(text), {"configurable": {"thread_id": text}},
            context={"authenticated_customer_id": 1}, durability="sync")
        assert not result.get("ticket_id")
    repo.create_ticket.assert_not_called()


def test_missing_preparation_checkpoint_prevents_write(network, database, monkeypatch):
    module, _ = network
    repo = database[0]
    repo.create_ticket = MagicMock()
    saver = MemorySaver()
    original = saver.get_tuple
    def missing(config):
        checkpoint = original(config)
        # Allow initialization but deny the executor's confirmation read.
        if checkpoint and set(config) == {"configurable"} and config["configurable"].get("checkpoint_ns") == "":
            return None
        return checkpoint
    monkeypatch.setattr(saver, "get_tuple", missing)
    graph = module.build_graph(checkpointer=saver, financial_repository=repo, ticket_writes=True)
    config = {"configurable": {"thread_id": "missing-checkpoint"}}
    graph.invoke(initial("Mi laptop no enciende"), config,
        context={"authenticated_customer_id": 1}, durability="sync")
    with pytest.raises(RuntimeError, match="checkpoint"):
        graph.invoke(None, config, context={"authenticated_customer_id": 1}, durability="sync")
    repo.create_ticket.assert_not_called()


def test_sales_intake_quantity_reaches_actual_inventory_tool(network, database):
    module, controls = network
    repo = database[0]
    controls["handlers"]["ventas"] = lambda messages: call("solicitar_inventario", consulta="SSD 500GB SATA")
    graph = module.build_graph(checkpointer=MemorySaver(), financial_repository=repo, ticket_writes=True)
    result = graph.invoke(initial("Quiero comprar dos SSD 500GB SATA"),
        {"configurable": {"thread_id": "sale-quantity"}}, context={"authenticated_customer_id": 1}, durability="sync")
    result = graph.invoke(None, {"configurable": {"thread_id": "sale-quantity"}},
        context={"authenticated_customer_id": 1}, durability="sync")
    assert controls["inventory_calls"] == [("SSD 500GB SATA", 2)]
    assert result["required_parts"] == [{"name": "SSD 500GB SATA", "quantity": 2}]
    assert result["current_agent"] == "ventas" and result["ticket_id"]
    assert result.get("quote_id") is None
    pairs(result)
    revised = graph.invoke({"messages": [HumanMessage(content="Quiero tres en lugar de dos")], "customer_id": 1},
        {"configurable": {"thread_id": "sale-quantity"}}, context={"authenticated_customer_id": 1}, durability="sync")
    assert controls["inventory_calls"] == [("SSD 500GB SATA", 2), ("SSD 500GB SATA", 3)]
    assert revised["ticket_id"] == result["ticket_id"]
    assert revised["request_revision"] == result["request_revision"] + 1
    assert all(row["quantity"] == 3 for row in revised["inventory_results"])
    pairs(revised)


def test_confirmed_quote_blocks_silent_quantity_change(network):
    module, controls = network
    result = module.ventas_node(dict(messages=[HumanMessage(content="Quiero tres en lugar de dos")],
        ticket_id=1, request_type="SALE", quote_id=2, intake={"quantity": 2}))
    assert not result["messages"][0].tool_calls
    assert "revisión comercial" in result["messages"][0].content
    assert not controls["inventory_calls"]


@pytest.mark.parametrize("stock,expected", [(3, ["ventas", "almacen", "ventas"]),
                                            (1, ["ventas", "almacen", "compras", "ventas"])])
def test_confirmed_sale_intake_drives_inventory_without_model_routing(network, database, stock, expected):
    module, controls = network
    repo, engine, _, _, quotes, *_ = database
    controls["inventory_stock"] = stock
    graph = module.build_graph(checkpointer=MemorySaver(), financial_repository=repo, ticket_writes=True)
    config = {"configurable": {"thread_id": "stock-"+str(stock)}}
    graph.invoke(initial("Quiero comprar dos SSD 500GB SATA"), config,
                 context={"authenticated_customer_id": 1}, durability="sync")
    result = graph.invoke(None, config, context={"authenticated_customer_id": 1}, durability="sync")
    assert [item["destination"] for item in result["handoff_history"]] == expected
    assert controls["inventory_calls"] == [("SSD 500GB SATA", 2)]
    assert bool(result.get("out_of_stock_items")) == (stock < 2)
    assert result.get("quote_id") is None and result.get("payment_id") is None
    with engine.connect() as conn:
        assert conn.scalar(select(func.count()).select_from(quotes)) == 0
    pairs(result)


def test_authenticated_http_exposes_only_confirmed_ticket_and_preserves_it(network, env):
    from contextlib import nullcontext
    from types import SimpleNamespace
    from fastapi.testclient import TestClient
    from app.accounts.session import SessionGuard
    from test_pattern_api import TestOwners
    module, controls = network
    controls["handlers"]["tecnico"] = lambda messages: AIMessage(content="Orientación preliminar")
    repo = MagicMock()
    repo.create_ticket.side_effect = lambda **payload: {**payload, "id": 100, "status": "NEW"}
    graph = module.build_graph(checkpointer=MemorySaver(), financial_repository=repo, ticket_writes=True)
    accounts, _, factory = env
    app = main.create_app(session_guard=SessionGuard(SETTINGS, factory),
        graph_factories={name: lambda: graph for name in main.PATTERN_NAMES},
        financial_repository=repo, conversation_owners_repository=TestOwners(),
        conversation_locks=SimpleNamespace(hold=lambda thread: nullcontext()), trace_context_factory=nullcontext)
    with TestClient(app) as client:
        assert client.post("/api/chat", json={"pattern": "decentralized", "message": "Mi laptop no enciende"}).status_code == 401
        client.cookies.set("techfix_session", login(accounts, "ana@demo.pe"))
        first = client.post("/api/chat", json={"pattern": "decentralized", "message": "Mi laptop no enciende", "customer_id": 99})
        assert first.status_code == 200, first.text
        data = first.json()
        assert "ticket" not in data
        repo.create_ticket.assert_not_called()
        separate = client.post("/api/chat", json={"pattern": "decentralized", "message": "Mi laptop no enciende"}).json()
        changed = client.post("/api/chat", json={"pattern": "decentralized", "conversation_id": separate["conversation_id"], "message": "Cambia el problema"})
        assert changed.status_code == 409
        repo.create_ticket.assert_not_called()
        blocked = client.post("/api/chat", json={"pattern": "decentralized", "conversation_id": separate["conversation_id"], "message": "Continuar"})
        assert blocked.status_code == 409
        repo.create_ticket.assert_not_called()
        confirmed = client.post("/api/chat", json={"pattern": "decentralized", "conversation_id": data["conversation_id"], "message": "Continuar"})
        assert confirmed.status_code == 200, confirmed.text
        assert repo.create_ticket.call_args.kwargs["customer_id"] == 1
        data = confirmed.json()
        assert data["ticket"] == {"code": repo.create_ticket.call_args.kwargs["code"], "status": "NEW"}
        second = client.post("/api/chat", json={"pattern": "decentralized", "conversation_id": data["conversation_id"], "message": "Continuar"})
        assert second.status_code == 200 and second.json()["ticket"] == data["ticket"]
        repo.create_ticket.assert_called_once()
