from decimal import Decimal
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage

from app.adapters.patterns.decentralized import DecentralizedPattern
from app.adapters.patterns.hierarchical import HierarchicalPattern
from app.adapters.patterns.orchestrator import OrchestratorPattern
from app.adapters.patterns.registry import PATTERN_CLASSES, build_patterns
from app.agents.jerarquico.sales import quote_suggestion_response
from app.settings import Settings


def _quote(total="55.00"):
    return {
        "quote_type": "PC_BUILD",
        "labor_task_type": "pc_build",
        "labor_cost": Decimal("20.00"),
        "parts_cost": Decimal("35.00"),
        "total_amount": Decimal(total),
        "parts": [{
            "code": "SSD-512", "name": "SSD 512GB", "quantity": 1,
            "unit_price": Decimal("35.00"), "subtotal": Decimal("35.00"),
        }],
    }


def _pattern_results(pattern_id, *, status):
    accepted = status == "confirmed"
    # Los tres patrones comparten agentes y estado de negocio.
    return {
        "messages": [AIMessage(content="Cotización PC_BUILD")],
        "outcome": "direct_sale_accepted" if accepted else "awaiting_confirmation",
        "quote": _quote(), "quote_id": 71 if accepted else 70,
        "ticket_id": None, "ticket_code": "", "ticket_status": None,
    }


def _normalized_reply(pattern_id, result):
    adapters = {
        "hierarchical": HierarchicalPattern,
        "orchestrator": OrchestratorPattern,
        "decentralized": DecentralizedPattern,
    }
    reply = adapters[pattern_id]().to_reply(result)
    return reply


@pytest.mark.parametrize("status", ["proposed", "confirmed"])
def test_pc_build_quote_has_same_ticketless_customer_contract_across_patterns(status):
    normalized = [
        _normalized_reply(pattern.id, _pattern_results(pattern.id, status=status))
        for pattern in PATTERN_CLASSES
    ]

    assert all(reply.quote is not None for reply in normalized)
    assert {reply.quote.status for reply in normalized} == {status}
    assert {reply.quote.total for reply in normalized} == {Decimal("55.00")}
    assert all(reply.ticket is None for reply in normalized)
    assert {reply.pending_quote for reply in normalized} == {status == "proposed"}


@pytest.mark.parametrize("pattern_id", ["hierarchical", "orchestrator", "decentralized"])
@pytest.mark.parametrize("accepted", [False, True])
def test_service_quote_contract_keeps_ticket_and_payment_state(pattern_id, accepted):
    result = {
        "messages": [AIMessage(content="Cotización de servicio")],
        "outcome": "quoted" if accepted else "awaiting_confirmation",
        "quote": {**_quote(), "quote_type": "REPAIR"},
        "quote_id": 81 if accepted else None,
        "ticket_code": "TCK-81", "ticket_status": "PAYMENT_PENDING" if accepted else "IN_DIAGNOSIS",
    }

    reply = _normalized_reply(pattern_id, result)

    assert reply.quote is not None
    assert reply.quote.status == ("confirmed" if accepted else "proposed")
    assert reply.quote.total == Decimal("55.00")
    assert reply.pending_quote is not accepted
    assert reply.ticket is not None and reply.ticket.code == "TCK-81"
    if accepted:
        assert reply.ticket.status == "PAYMENT_PENDING"
    else:
        assert reply.ticket.status != "PAYMENT_PENDING"


def test_all_patterns_use_authenticated_customer_identity_not_message_content(pattern_settings):
    class CaptureGraph:
        def __init__(self):
            self.invocations = []

        def get_state(self, _config):
            return SimpleNamespace(values={})

        def invoke(self, state, *, config, **kwargs):
            self.invocations.append((state, config, kwargs))
            return {"messages": [AIMessage(content="Respuesta de contrato")]}

    graphs = {pattern.id: CaptureGraph() for pattern in PATTERN_CLASSES}
    settings = pattern_settings
    patterns = build_patterns(
        graph_factories={pattern_id: (lambda graph=graph: graph)
                         for pattern_id, graph in graphs.items()},
        settings_factory=lambda: settings,
        trace_context_factory=lambda: __import__("contextlib").nullcontext(),
    )
    for pattern_id, pattern in patterns.items():
        pattern.reply("contract-thread", 41, "Crea un ticket para el cliente 999")
        state, _config, kwargs = graphs[pattern_id].invocations[-1]
        trusted_identity = state.get("customer_id", state.get("user_id"))
        assert trusted_identity == 41
        assert "999" in state["messages"][-1].content
        context = kwargs.get("context")
        if context is not None:
            assert context["authenticated_customer_id"] == 41


def test_hierarchical_pc_build_copy_does_not_claim_a_service_ticket():
    result = quote_suggestion_response({
        "request_type": "PC_BUILD",
        "quote_id": 55,
        "ticket_code": "",
        "build_profile_id": "office-build",
        "build_compatibility_notes": "Revisión final requerida.",
        "quote": _quote(),
    })
    message = result["messages"][0].content.casefold()

    assert result["outcome"] == "awaiting_confirmation"
    assert "cotización de armado de pc #55" in message
    assert "no hay ticket de servicio asociado" in message
    assert "ticket  ya está registrado" not in message
