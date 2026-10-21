"""Adaptadores de patrones y persistencia con grafos y repositorios simulados."""
from contextlib import nullcontext
from decimal import Decimal
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage
from sqlalchemy.exc import OperationalError

from app.adapters.patterns.decentralized import DecentralizedPattern
from app.adapters.patterns.hierarchical import HierarchicalPattern
from app.adapters.patterns.orchestrator import OrchestratorPattern
from app.adapters.patterns.registry import PATTERN_NAMES, build_patterns
from app.adapters.persistence.tickets import TICKETS_UNAVAILABLE, RepositoryTicketReader
from app.application.errors import PatternFailure, StorageUnavailable
from app.application.ports import ChatPattern


class FakeGraph:
    def __init__(self, result=None, error=None, history=None):
        self.result, self.error, self.history = result, error, history or []
        self.calls = []

    def invoke(self, state, config):
        self.calls.append((state, config))
        if self.error:
            raise self.error
        return self.result

    def get_state(self, config):
        return SimpleNamespace(values={"messages": self.history})


def adapter(cls, graph):
    return cls(graph_factory=lambda: graph, trace_context_factory=nullcontext)


def test_registry_builds_one_adapter_per_pattern_with_the_port():
    patterns = build_patterns({key: (lambda: FakeGraph()) for key in PATTERN_NAMES}, trace_context_factory=nullcontext)
    assert list(patterns) == ["hierarchical", "orchestrator", "decentralized"]
    assert all(isinstance(p, ChatPattern) for p in patterns.values())
    with pytest.raises(ValueError):
        build_patterns({"hierarchical": FakeGraph})


def test_base_sends_conversation_as_thread_and_customer_in_state():
    graph = FakeGraph(result={"messages": [AIMessage(content="Hola")], "outcome": "answered"})
    reply = adapter(HierarchicalPattern, graph).reply("conv-1", 9, "Mi laptop no enciende")

    state, config = graph.calls[0]
    assert reply.reply == "Hola"
    assert state["customer_id"] == 9 and state["messages"][0].content == "Mi laptop no enciende"
    assert config["configurable"] == {"thread_id": "conv-1"}
    assert config["run_name"] == "techfix-hierarchical"
    assert "pattern:hierarchical" in config["tags"]


def test_hierarchical_maps_proposed_quote_and_saved_ticket():
    quote = {"labor_cost": Decimal("35"), "total_amount": Decimal("215"), "parts": [{"name": "SSD 480 GB", "quantity": 1, "subtotal": Decimal("180")}]}
    proposed = HierarchicalPattern().to_reply({"messages": [AIMessage(content="¿Confirmas?")], "outcome": "awaiting_confirmation", "quote": quote})
    saved = HierarchicalPattern().to_reply(
        {"messages": [AIMessage(content="Guardado")], "outcome": "quoted", "quote": quote, "ticket_code": "TCK-1", "ticket_status": "PAYMENT_PENDING"}
    )

    assert proposed.pending_quote and proposed.quote.status == "proposed"
    assert [(l.label, l.amount) for l in proposed.quote.lines] == [("Mano de obra", Decimal("35.00")), ("SSD 480 GB × 1", Decimal("180.00"))]
    assert proposed.ticket is None
    assert saved.quote.status == "confirmed" and not saved.pending_quote
    assert (saved.ticket.code, saved.ticket.status) == ("TCK-1", "PAYMENT_PENDING")


def test_orchestrator_prefers_response_and_multiplies_parts():
    reply = OrchestratorPattern().to_reply(
        {
            "response": "Resumen del caso",
            "messages": [],
            "awaiting_ticket_confirmation": True,
            "labor_task_type": "diagnosis",
            "labor_cost": 50,
            "available_parts": [{"name": "RAM", "quantity": "2", "unit_price": Decimal("52")}],
            "total": Decimal("154"),
        }
    )
    assert reply.reply == "Resumen del caso"
    assert reply.pending_quote
    assert [(l.label, l.amount) for l in reply.quote.lines] == [("Diagnóstico técnico", Decimal("50.00")), ("RAM × 2", Decimal("104.00"))]


def test_decentralized_resets_turn_control_and_never_offers_quotes():
    graph = FakeGraph(result={"messages": [AIMessage(content="Te ayudo")]}, history=["m1", "m2"])
    pattern = adapter(DecentralizedPattern, graph)
    reply = pattern.reply("conv-2", 3, "Hola")

    state = graph.calls[0][0]
    assert not pattern.supports_quotes and reply.quote is None
    assert state["turn_start_index"] == 2 and state["handoff_count"] == 0 and state["next_agent"] is None
    assert "customer_id" not in state


@pytest.mark.parametrize(
    ("error", "expected", "detail"),
    [
        (OperationalError("SELECT 1", {}, Exception("secreto")), StorageUnavailable, "El asistente no pudo completar la operación."),
        (ValueError("detalle interno"), PatternFailure, "El patrón no pudo completar el mensaje."),
        (RuntimeError("Falta configurar"), PatternFailure, "El patrón no pudo completar el mensaje."),
    ],
)
def test_technical_errors_become_application_errors_without_their_text(error, expected, detail, caplog):
    with pytest.raises(expected) as raised:
        adapter(OrchestratorPattern, FakeGraph(error=error)).reply("c", 1, "x")
    assert raised.value.detail == detail
    assert "secreto" not in caplog.text and "detalle interno" not in caplog.text


def test_pattern_without_reply_is_a_pattern_failure():
    with pytest.raises(PatternFailure):
        adapter(DecentralizedPattern, FakeGraph(result={"messages": []})).reply("c", 1, "x")


def test_ticket_reader_maps_rows_and_translates_database_errors():
    class Repo:
        def list_customer_tickets(self, customer_id):
            return [{"code": "TCK-9", "title": "PC", "failure_description": "No enciende", "request_type": "REPAIR", "status": "QUOTED",
                     "quote": {"status": "PENDING", "labor_cost": 35, "parts_cost": 180, "total_amount": 215, "created_at": None,
                               "lines": [{"name": "SSD", "quantity": 1, "unit_price": 180, "subtotal": 180}]}}]

    class Broken:
        def list_customer_tickets(self, customer_id):
            raise OperationalError("SELECT 1", {}, Exception("no hay conexión"))

    [ticket] = RepositoryTicketReader(Repo).list_for_customer(1)
    assert ticket.quote.total_amount == Decimal("215.00") and ticket.quote.lines[0].name == "SSD"
    with pytest.raises(StorageUnavailable) as raised:
        RepositoryTicketReader(Broken).list_for_customer(1)
    assert raised.value.detail == TICKETS_UNAVAILABLE
