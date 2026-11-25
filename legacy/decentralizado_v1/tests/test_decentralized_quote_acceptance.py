"""Aceptación real del endpoint con grafo/repositorio reales y SQLite sintético."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager, nullcontext
from copy import deepcopy
from decimal import Decimal
from threading import Event, Lock
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from sqlalchemy import create_engine, select, func, event
from sqlalchemy.pool import StaticPool

from app.agents.decentralized.policy import build_verified_quote
from app.agents.decentralized.quote_operations import (
    QuoteConflict, apply_quote_action, build_proposal, prepare_quote_decision,
    validate_pending_quote, validate_proposal,
)
from app.accounts.session import SessionGuard
from app.database.conversation_locks import ConversationBusy
from app.database.conversation_owners import ConversationNotFound
from app.main import create_app, PATTERN_NAMES
from test_session_guard import env, login, SETTINGS
from test_software_e2e import network


@pytest.fixture
def quote_database(monkeypatch):
    import test_decentralized_repository as fixtures
    monkeypatch.setattr(fixtures, "create_engine", lambda *args, **kwargs: create_engine(
        "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}))
    generator = fixtures.database.__wrapped__()
    value = next(generator)
    yield value
    try:
        next(generator)
    except StopIteration:
        pass


def commercial_state(repo, *, customer=1, conversation="quote-conversation", quantity=2):
    ticket = repo.create_ticket(customer_id=customer, code="TCK-QUOTE-TEST", title="SSD solicitado",
                              failure_description="Dos SSD de prueba", request_type="SALE")
    item = repo.get_inventory(spare_part_id=1, quantity=quantity)
    result = dict(requested_name="SSD de prueba", name=item["name"], quantity=quantity,
                  stock=item["current_stock"], unit_price=str(item["unit_price"]),
                  available=item["available"], inventory_id=item["id"], found=True, tool_call_id="catalog")
    state = dict(messages=[HumanMessage(content="Quiero estos SSD")], current_agent="ventas",
                 customer_id=customer, ticket_id=ticket["id"], ticket_code=ticket["code"], ticket_status=ticket["status"],
                 request_type="SALE", request_revision=0, inventory_revision=0, inventory_pending=False,
                 required_parts=[dict(name="SSD de prueba", quantity=quantity)], inventory_results=[result], quote_scope="repuestos")
    quote, _ = build_verified_quote([result], [], request_type="SALE")
    state["quote"] = quote
    state["proposal"] = build_proposal(state, quote, authenticated_customer_id=customer,
                                      conversation_id=conversation, repository=repo)
    return state


@pytest.fixture
def quote_graph(network, quote_database):
    module, controls = network
    repo, engine, tickets, parts, quotes, details = quote_database
    repo.create_pending_payment = MagicMock(side_effect=AssertionError("No financial writes"))
    saver = MemorySaver()
    graph = module.build_graph(checkpointer=saver, financial_repository=repo, quote_writes=True)
    state = commercial_state(repo)
    config = {"configurable": {"thread_id": "quote-thread"}, "metadata": {"conversation_id": "quote-conversation"}}
    graph.update_state(config, state, as_node="ventas")
    yield SimpleNamespace(module=module, graph=graph, state=state, config=config, repo=repo, engine=engine,
                          quotes=quotes, details=details, parts=parts, tickets=tickets, saver=saver, controls=controls)
    repo.create_pending_payment.assert_not_called()


def action(value, name="accept_quote", **changes):
    return apply_quote_action(value.graph, value.config, **{
        **dict(authenticated_customer_id=1, conversation_id="quote-conversation",
               proposal_id=value.state["proposal"]["proposal_id"], action=name), **changes})


def count(value):
    with value.engine.connect() as connection:
        return connection.scalar(select(func.count()).select_from(value.quotes))


def test_proposal_id_stable_and_exact(quote_graph):
    value = quote_graph
    before = deepcopy(value.state)
    proposal = build_proposal(value.state, value.state["quote"], authenticated_customer_id=1,
                              conversation_id="quote-conversation", repository=value.repo)
    assert proposal == value.state["proposal"] and value.state == before
    assert proposal["lines"][0]["spare_part_id"] == 1
    assert proposal["total_amount"] == Decimal("360.00")
    assert count(value) == 0


@pytest.mark.parametrize("customer", [None, True, 0, -1, "1", 2])
def test_identity_cannot_be_selected_from_state(quote_graph, customer):
    with pytest.raises((QuoteConflict, ValueError)):
        action(quote_graph, authenticated_customer_id=customer)
    assert count(quote_graph) == 0


@pytest.mark.parametrize("changes", [dict(proposal_id=None), dict(proposal_id="old"),
                                    dict(conversation_id="another-conversation")])
def test_missing_old_or_foreign_proposal_rejected(quote_graph, changes):
    with pytest.raises(QuoteConflict):
        action(quote_graph, **changes)
    assert count(quote_graph) == 0


def test_old_revision_and_changed_quantity_cannot_accept(quote_graph):
    value = quote_graph
    value.graph.update_state(value.config, {"request_revision": 1})
    with pytest.raises(QuoteConflict):
        action(value)
    assert count(value) == 0
    newer = {**value.state, "request_revision": 1, "inventory_revision": 1}
    newer["inventory_results"] = [{**value.state["inventory_results"][0], "quantity": 1}]
    newer["required_parts"] = [dict(name="SSD de prueba", quantity=1)]
    quote, _ = build_verified_quote(newer["inventory_results"], [], request_type="SALE")
    proposal = build_proposal(newer, quote, authenticated_customer_id=1, conversation_id="quote-conversation", repository=value.repo)
    assert proposal["proposal_id"] != value.state["proposal"]["proposal_id"]


@pytest.mark.parametrize("change", [dict(current_stock=0), dict(current_stock=2), dict(unit_price=Decimal("181.00"))])
def test_initial_acceptance_requires_unchanged_stock_and_price(quote_graph, change):
    value = quote_graph
    with value.engine.begin() as connection:
        connection.execute(value.parts.update().where(value.parts.c.id == 1).values(**change))
    with pytest.raises(QuoteConflict):
        action(value)
    assert count(value) == 0
    assert value.graph.get_state(value.config).values.get("pending_quote_operation") is None


def test_preparation_checkpoint_exists_before_repository_and_commit_reply(quote_graph, monkeypatch):
    value = quote_graph
    original = value.repo.create_accepted_quote
    def persist(**payload):
        saved = value.graph.get_state(value.config).values
        pending = saved["pending_quote_operation"]
        assert pending["payload"] == payload
        assert saved.get("quote_id") is None and saved.get("quote_receipt") is None
        assert "todavía no" in saved["messages"][-1].content
        return original(**payload)
    monkeypatch.setattr(value.repo, "create_accepted_quote", persist)
    result = action(value)
    assert count(value) == 1 and result["quote_status"] == "ACCEPTED"
    assert result["pending_quote_operation"] is None and result["quote_receipt"]["quote_id"] == result["quote_id"]
    assert "guardada" in result["messages"][-1].content and not result.get("payment_id")
    assert action(value)["quote_id"] == result["quote_id"] and count(value) == 1


def test_rejection_and_rejection_retry_never_write(quote_graph):
    value = quote_graph
    result = action(value, "reject_quote")
    assert result["quote"]["status"] == "rejected" and count(value) == 0
    assert action(value, "reject_quote")["proposal_decision"]["accepted"] is False
    with pytest.raises(QuoteConflict):
        action(value)


@pytest.mark.parametrize("after_commit", [False, True])
def test_exception_recovery_recreates_graph_and_reuses_exact_pending_payload(quote_graph, monkeypatch, after_commit):
    value = quote_graph
    original = value.repo.create_accepted_quote
    calls = []
    def fail(**payload):
        calls.append(deepcopy(payload))
        if after_commit:
            original(**payload)
        raise RuntimeError("synthetic storage interruption")
    monkeypatch.setattr(value.repo, "create_accepted_quote", fail)
    with pytest.raises(RuntimeError):
        action(value)
    saved = value.graph.get_state(value.config).values
    pending = deepcopy(saved["pending_quote_operation"])
    assert pending["payload"] == calls[0] and saved.get("quote_id") is None
    assert count(value) == int(after_commit)
    with pytest.raises(QuoteConflict):
        action(value, "reject_quote")
    assert value.graph.get_state(value.config).values["pending_quote_operation"] == pending
    monkeypatch.setattr(value.repo, "create_accepted_quote", original)
    value.graph = value.module.build_graph(checkpointer=value.saver, financial_repository=value.repo, quote_writes=True)
    if after_commit:
        with value.engine.begin() as connection:
            connection.execute(value.parts.update().where(value.parts.c.id == 1).values(unit_price=999, current_stock=0))
    recovered = action(value)
    assert recovered["quote_receipt"]["payload"] == calls[0]
    assert count(value) == 1 and recovered["quote_status"] == "ACCEPTED"


def test_rollback_on_detail_failure_keeps_operation_and_ticket(quote_graph):
    value = quote_graph
    def fail(connection, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO quote_details"):
            raise RuntimeError("synthetic detail failure")
    event.listen(value.engine, "before_cursor_execute", fail)
    try:
        with pytest.raises(RuntimeError):
            action(value)
    finally:
        event.remove(value.engine, "before_cursor_execute", fail)
    assert count(value) == 0
    assert value.repo.get_ticket(customer_id=1, ticket_id=value.state["ticket_id"])["status"] == "NEW"
    assert value.graph.get_state(value.config).values["pending_quote_operation"]
    assert action(value)["quote_status"] == "ACCEPTED" and count(value) == 1


@pytest.mark.parametrize("different", [False, True])
def test_concurrent_prepared_conversations_share_ticket_without_duplicates(quote_graph, monkeypatch, different):
    """SQLite no ofrece FOR UPDATE: el lock simula el bloqueo de fila PostgreSQL."""
    value = quote_graph
    second = deepcopy(value.state)
    if different:
        second["required_parts"][0]["quantity"] = 1
        second["inventory_results"][0]["quantity"] = 1
        second["quote"], _ = build_verified_quote(second["inventory_results"], [], request_type="SALE")
    second["proposal"] = build_proposal(second, second["quote"], authenticated_customer_id=1,
        conversation_id="second-conversation", repository=value.repo)
    second_config = {"configurable": {"thread_id": "second-thread"}, "metadata": {"conversation_id": "second-conversation"}}
    value.graph.update_state(second_config, second, as_node="ventas")
    for config, state, conversation in [(value.config, value.state, "quote-conversation"), (second_config, second, "second-conversation")]:
        value.graph.invoke({}, config, context=dict(authenticated_customer_id=1, quote_action="accept_quote",
            quote_conversation_id=conversation, quote_proposal_id=state["proposal"]["proposal_id"]), durability="sync")
    row_lock = Lock()
    original = value.repo.create_accepted_quote
    def serialized(**payload):
        with row_lock:
            return original(**payload)
    monkeypatch.setattr(value.repo, "create_accepted_quote", serialized)
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(apply_quote_action, value.graph, config,
            authenticated_customer_id=1, conversation_id=conversation,
            proposal_id=state["proposal"]["proposal_id"], action="accept_quote")
            for config, state, conversation in [(value.config, value.state, "quote-conversation"), (second_config, second, "second-conversation")]]
        results, errors = [], []
        for future in futures:
            try:
                results.append(future.result(timeout=10))
            except QuoteConflict as exc:
                errors.append(exc)
            except ValueError as exc:
                # RetryConflict belongs to the existing repository contract.
                from app.database.decentralized_repository import RetryConflict
                assert isinstance(exc, RetryConflict)
                errors.append(exc)
    assert count(value) == 1
    assert len(errors) == int(different) and len(results) == (1 if different else 2)
    if not different:
        assert results[0]["quote_id"] == results[1]["quote_id"]


def test_pending_content_cannot_be_overwritten_or_rejected(quote_graph):
    value = quote_graph
    context = dict(authenticated_customer_id=1, quote_action="accept_quote", quote_conversation_id="quote-conversation",
                   quote_proposal_id=value.state["proposal"]["proposal_id"])
    value.graph.invoke({}, value.config, context=context, durability="sync")
    before = deepcopy(value.graph.get_state(value.config).values["pending_quote_operation"])
    with pytest.raises(QuoteConflict):
        action(value, "reject_quote")
    with pytest.raises(QuoteConflict):
        action(value, proposal_id="different")
    assert value.graph.get_state(value.config).values["pending_quote_operation"] == before
    assert count(value) == 0


@pytest.mark.parametrize("checkpoint_committed", [False, True])
def test_checkpoint_failure_after_sql_commit_can_be_recovered(quote_graph, monkeypatch, checkpoint_committed):
    value = quote_graph
    original_put = value.saver.put
    def fail(config, checkpoint, metadata, versions):
        if checkpoint["channel_values"].get("quote_receipt"):
            if checkpoint_committed:
                original_put(config, checkpoint, metadata, versions)
            raise RuntimeError("synthetic checkpoint interruption")
        return original_put(config, checkpoint, metadata, versions)
    monkeypatch.setattr(value.saver, "put", fail)
    with pytest.raises(RuntimeError):
        action(value)
    assert count(value) == 1
    monkeypatch.setattr(value.saver, "put", original_put)
    value.graph = value.module.build_graph(checkpointer=value.saver, financial_repository=value.repo, quote_writes=True)
    result = action(value)
    assert result["quote_status"] == "ACCEPTED" and count(value) == 1


@pytest.mark.parametrize("kind", ["REPAIR", "SUPPORT"])
def test_service_only_acceptance_preserves_sql_type_and_approved_labor(quote_graph, kind):
    value = quote_graph
    with value.engine.begin() as connection:
        connection.execute(value.tickets.update().where(value.tickets.c.id == value.state["ticket_id"]).values(request_type=kind))
    state = {**value.state, "request_type": kind, "required_parts": [], "inventory_results": [], "quote_scope": "solo_servicio"}
    state["quote"], _ = build_verified_quote([], [], scope="solo_servicio", request_type=kind)
    state["proposal"] = build_proposal(state, state["quote"], authenticated_customer_id=1, conversation_id="quote-conversation", repository=value.repo)
    value.state = state
    value.graph.update_state(value.config, state, as_node="ventas")
    result = action(value)
    saved = value.repo.get_quote(customer_id=1, quote_id=result["quote_id"])
    assert saved["quote_type"] == "REPAIR" and saved["total_amount"] == Decimal("35.00")
    assert saved["lines"] == [] and saved["observations"] == ("SUPPORT" if kind == "SUPPORT" else None)


def test_pending_payload_conflict_cannot_change_existing_operation(quote_graph):
    value = quote_graph
    context = dict(authenticated_customer_id=1, quote_action="accept_quote", quote_conversation_id="quote-conversation",
                   quote_proposal_id=value.state["proposal"]["proposal_id"])
    value.graph.invoke({}, value.config, context=context, durability="sync")
    saved = value.graph.get_state(value.config).values
    changed = deepcopy(saved)
    changed["pending_quote_operation"]["payload"]["lines"][0]["quantity"] = 1
    with pytest.raises(QuoteConflict):
        validate_pending_quote(changed, authenticated_customer_id=1, conversation_id="quote-conversation",
                               proposal_id=context["quote_proposal_id"])
    assert value.graph.get_state(value.config).values["pending_quote_operation"] == saved["pending_quote_operation"]
    assert count(value) == 0


def test_ticket_ownership_is_rechecked_before_acceptance(quote_graph):
    value = quote_graph
    with value.engine.begin() as connection:
        connection.execute(value.tickets.update().where(value.tickets.c.id == value.state["ticket_id"]).values(customer_id=2))
    with pytest.raises(LookupError):
        action(value)
    assert count(value) == 0


def test_missing_checkpoint_evidence_blocks_write(quote_graph, monkeypatch):
    value = quote_graph
    original = value.repo.create_accepted_quote
    def attempt(**payload):
        raise AssertionError("must not execute")
    # Prepare legitimately, then remove only the evidence read by the executor.
    context = dict(authenticated_customer_id=1, quote_action="accept_quote", quote_conversation_id="quote-conversation",
                   quote_proposal_id=value.state["proposal"]["proposal_id"])
    value.graph.invoke({}, value.config, context=context, durability="sync")
    assert value.graph.get_state(value.config).next == ("ejecutar_cotizacion",)
    original_tuple = value.saver.get_tuple
    def altered(config):
        item = original_tuple(config)
        if item is None:
            return item
        checkpoint = deepcopy(item.checkpoint)
        checkpoint["channel_values"].pop("pending_quote_operation", None)
        return item._replace(checkpoint=checkpoint)
    monkeypatch.setattr(value.repo, "create_accepted_quote", attempt)
    # Executor validation also rejects a snapshot without the original operation.
    with monkeypatch.context() as patch:
        patch.setattr(value.saver, "get_tuple", altered)
        with pytest.raises((QuoteConflict, ValueError)):
            value.graph.invoke(None, value.config, context=context, durability="sync")
    monkeypatch.setattr(value.repo, "create_accepted_quote", original)
    assert count(value) == 0


@pytest.fixture
def quote_api(quote_graph, env):
    accounts, _, factory = env
    value = quote_graph
    owners = MagicMock()
    def authorize(**kwargs):
        if kwargs["authenticated_customer_id"] != 1:
            raise ConversationNotFound()
        return dict(thread_id="quote-thread")
    owners.authorize.side_effect = authorize
    lock = Lock()
    @contextmanager
    def hold(thread):
        if not lock.acquire(blocking=False):
            raise ConversationBusy()
        try:
            yield
        finally:
            lock.release()
    app = create_app(session_guard=SessionGuard(SETTINGS, factory), financial_repository=value.repo,
        graph_factories={name: lambda: value.graph for name in PATTERN_NAMES},
        conversation_owners_repository=owners, conversation_locks=SimpleNamespace(hold=hold),
        trace_context_factory=nullcontext)
    with TestClient(app) as client:
        client.cookies.set("techfix_session", login(accounts, "ana@demo.pe"))
        yield client, value, accounts


def body(value, **changes):
    return {**dict(pattern="decentralized", conversation_id="quote-conversation", action="accept_quote",
                   proposal_id=value.state["proposal"]["proposal_id"]), **changes}


def test_http_preview_accept_retry_and_no_financial_writes(quote_api):
    client, value, _ = quote_api
    preview = client.post("/api/chat", json=body(value, action=None, proposal_id=None, message="¿Cuál es el total propuesto?"))
    assert preview.status_code == 200
    assert preview.json()["quote"]["proposal_id"] == value.state["proposal"]["proposal_id"]
    response = client.post("/api/chat", json=body(value, customer_id=2, amount="0.01", total="0.01"))
    assert response.status_code == 200 and response.json()["quote"]["status"] == "confirmed"
    assert response.json()["quote"]["total"] == "360.00" and count(value) == 1
    assert client.post("/api/chat", json=body(value)).status_code == 200 and count(value) == 1


@pytest.mark.parametrize("proposal_id", [None, "", "old-id"])
def test_http_requires_exact_id(quote_api, proposal_id):
    client, value, _ = quote_api
    response = client.post("/api/chat", json=body(value, proposal_id=proposal_id))
    assert response.status_code == 409 and count(value) == 0


def test_http_reject_then_accept_rejected_is_conflict(quote_api):
    client, value, _ = quote_api
    response = client.post("/api/chat", json=body(value, action="reject_quote"))
    assert response.status_code == 200 and response.json()["quote"]["status"] == "rejected"
    assert count(value) == 0 and client.post("/api/chat", json=body(value)).status_code == 409


def test_http_no_session_or_other_customer_cannot_accept(quote_api):
    client, value, accounts = quote_api
    client.cookies.clear()
    assert client.post("/api/chat", json=body(value)).status_code == 401
    accounts.post("/registro", json=dict(nombre="Otro cliente", email="other@example.test", telefono="+51922222222", password="TriageTech#2026"))
    client.cookies.set("techfix_session", login(accounts, "other@example.test"))
    assert client.post("/api/chat", json=body(value)).status_code == 404 and count(value) == 0


def test_http_concurrent_same_conversation_is_busy_without_second_write(quote_api, monkeypatch):
    client, value, _ = quote_api
    entered, release = Event(), Event()
    original = value.repo.create_accepted_quote
    def waiting(**payload):
        entered.set()
        assert release.wait(10)
        return original(**payload)
    monkeypatch.setattr(value.repo, "create_accepted_quote", waiting)
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(client.post, "/api/chat", json=body(value))
        try:
            assert entered.wait(10)
            second = client.post("/api/chat", json=body(value))
            assert second.status_code == 409 and second.json()["code"] == "conversation_busy"
        finally:
            release.set()
        assert first.result(timeout=10).status_code == 200
    assert count(value) == 1


def test_http_unknown_commit_retry_and_reject_preserve_pending(quote_api, monkeypatch):
    client, value, _ = quote_api
    original = value.repo.create_accepted_quote
    def unknown_commit(**payload):
        original(**payload)
        raise RuntimeError("synthetic connection interruption")
    monkeypatch.setattr(value.repo, "create_accepted_quote", unknown_commit)
    response = client.post("/api/chat", json=body(value))
    assert response.status_code == 502 and "confirmed" not in response.text
    pending = deepcopy(value.graph.get_state(value.config).values["pending_quote_operation"])
    assert count(value) == 1
    assert client.post("/api/chat", json=body(value, action="reject_quote")).status_code == 409
    assert value.graph.get_state(value.config).values["pending_quote_operation"] == pending
    assert client.post("/api/chat", json=body(value, action=None, message="Quiero cambiar cantidad")).status_code == 409
    monkeypatch.setattr(value.repo, "create_accepted_quote", original)
    retry = client.post("/api/chat", json=body(value))
    assert retry.status_code == 200 and retry.json()["quote"]["status"] == "confirmed" and count(value) == 1


def test_http_old_card_cannot_accept_replacement_proposal(quote_api):
    client, value, _ = quote_api
    newer = deepcopy(value.state)
    newer.update(request_revision=1, inventory_revision=1)
    newer["proposal"] = build_proposal(newer, newer["quote"], authenticated_customer_id=1,
        conversation_id="quote-conversation", repository=value.repo)
    value.graph.update_state(value.config, newer, as_node="ventas")
    response = client.post("/api/chat", json=body(value))
    assert response.status_code == 409 and count(value) == 0
    accepted = client.post("/api/chat", json=body(value, proposal_id=newer["proposal"]["proposal_id"]))
    assert accepted.status_code == 200 and count(value) == 1


def test_http_requires_recovery_before_new_input_after_checkpoint_failure(quote_api, monkeypatch):
    client, value, _ = quote_api
    original = value.saver.put
    def fail(config, checkpoint, metadata, versions):
        if checkpoint["channel_values"].get("quote_receipt"):
            raise RuntimeError("synthetic checkpoint failure")
        return original(config, checkpoint, metadata, versions)
    monkeypatch.setattr(value.saver, "put", fail)
    assert client.post("/api/chat", json=body(value)).status_code == 502
    assert count(value) == 1
    monkeypatch.setattr(value.saver, "put", original)
    assert client.post("/api/chat", json=body(value, action=None, message="Cambiar cantidad")).status_code == 409
    recovered = client.post("/api/chat", json=body(value))
    assert recovered.status_code == 200 and recovered.json()["quote"]["status"] == "confirmed"
    assert count(value) == 1


def test_http_checkpoint_storage_failure_preserves_pending_and_returns_503(quote_api, monkeypatch):
    from psycopg import OperationalError
    client, value, _ = quote_api
    original = value.repo.create_accepted_quote
    def interrupted(**payload):
        raise OperationalError("synthetic storage interruption")
    monkeypatch.setattr(value.repo, "create_accepted_quote", interrupted)
    response = client.post("/api/chat", json=body(value))
    assert response.status_code == 503
    assert "synthetic storage interruption" not in response.text
    pending = deepcopy(value.graph.get_state(value.config).values["pending_quote_operation"])
    assert pending["proposal_id"] == value.state["proposal"]["proposal_id"] and count(value) == 0
    monkeypatch.setattr(value.repo, "create_accepted_quote", original)
    retry = client.post("/api/chat", json=body(value))
    assert retry.status_code == 200 and retry.json()["quote"]["status"] == "confirmed"
    assert count(value) == 1
