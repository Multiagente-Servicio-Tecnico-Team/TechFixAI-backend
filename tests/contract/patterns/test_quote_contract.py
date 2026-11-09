from decimal import Decimal

import pytest

from app.application.ports import QuoteDraft, QuoteLineDraft
from app.adapters.tools.quotes import make_quote_calculation_tool
from app.application.catalog import CatalogService
from app.application.ports import CustomerContext
from app.application.quotes import interpret_quote_decision, quote_changed
from app.adapters.patterns.decentralized import DecentralizedPattern
from app.adapters.patterns.registry import PATTERN_CLASSES
from langchain_core.messages import AIMessage
from contextlib import nullcontext
from types import SimpleNamespace

from app.adapters.patterns.registry import build_patterns
from app.application.chat import SendChatMessage
from app.application.conversations import ConversationRegistry


def make_quote(unit_price: str = "35.50") -> QuoteDraft:
    price = Decimal(unit_price)
    return QuoteDraft(
        ticket_id=10,
        quote_type="REPAIR",
        labor_task_type="maintenance",
        labor_cost=Decimal("35.00"),
        parts_cost=price,
        total_amount=Decimal("35.00") + price,
        currency="PEN",
        lines=(QuoteLineDraft(4, 1, price, price),),
    )


def test_shared_quote_tool_detects_stale_price_before_customer_decision():
    class MutableCatalog:
        price = Decimal("35.50")

        def lookup_inventory(self, name, quantity):
            return {"requested_name": name, "name": name, "quantity": quantity,
                    "stock": 4, "unit_price": self.price,
                    "available": quantity <= 4, "found": True}

        def find_spare_parts(self, term): return []
        def find_catalog_items(self, term, *, limit=20): return []
        def find_spare_part_by_code(self, code):
            return {"id": 4, "code": code, "name": "SSD 512GB",
                    "category": "Almacenamiento", "unit_price": self.price,
                    "current_stock": 4}
        def find_spare_part_alternatives(self, term): return []

    repository = MutableCatalog()

    def quote_tool():
        return make_quote_calculation_tool(
            CatalogService(repository),
            customer_context=CustomerContext(41, "contract-conversation", "contract"),
            labor_task_type="maintenance",
            labor_cost=Decimal("35.00"),
            quote_type="REPAIR",
        )

    original = quote_tool().invoke({"parts": [{"code": "SSD-512", "quantity": 1}]})
    repository.price = Decimal("39.50")
    refreshed = quote_tool().invoke({"parts": [{"code": "SSD-512", "quantity": 1}]})

    assert quote_changed(original, refreshed) is True
    assert original["total_amount"] == Decimal("70.50")
    assert refreshed["total_amount"] == Decimal("74.50")
    assert interpret_quote_decision("puedo revisar antes de aceptar") is None


@pytest.mark.parametrize(
    "field,value",
    [
        ("unit_price", Decimal("39.50")),
        ("current_stock", 4),
        ("subtotal", Decimal("39.50")),
    ],
)
def test_quote_fingerprint_detects_each_inventory_change(field, value):
    original = {
        "quote_type": "REPAIR",
        "labor_task_type": "maintenance",
        "labor_cost": Decimal("35.00"),
        "parts_cost": Decimal("35.50"),
        "total_amount": Decimal("70.50"),
        "parts": [{"code": "SSD-512", "quantity": 1,
                   "unit_price": Decimal("35.50"), "current_stock": 5,
                   "subtotal": Decimal("35.50")}],
    }
    updated_line = {**original["parts"][0], field: value}
    updated = {**original, "parts": [updated_line]}

    assert quote_changed(original, updated) is True


def test_identical_quote_is_not_marked_stale():
    assert quote_changed(make_quote(), make_quote()) is False


def test_hierarchical_quote_mapping_detects_stock_and_price_changes():
    quote = {
        "quote_type": "REPAIR",
        "labor_task_type": "maintenance",
        "labor_cost": Decimal("35.00"),
        "parts_cost": Decimal("35.50"),
        "total_amount": Decimal("70.50"),
        "parts": [{
            "id": 4,
            "quantity": 1,
            "unit_price": Decimal("35.50"),
            "current_stock": 5,
            "subtotal": Decimal("35.50"),
        }],
    }
    changed = {**quote, "parts": [{**quote["parts"][0], "current_stock": 4}]}

    assert quote_changed(quote, changed) is True
    assert quote_changed(quote, quote.copy()) is False


def test_all_pattern_adapters_advertise_quote_actions():
    assert {pattern.id for pattern in PATTERN_CLASSES} == {
        "hierarchical", "orchestrator", "decentralized"
    }
    assert all(pattern.supports_quotes for pattern in PATTERN_CLASSES)


def test_decentralized_adapter_maps_proposed_quote_to_shared_reply():
    result = {
        "messages": [AIMessage(content="Cotización preliminar")],
        "quote": {
            "quote_type": "REPAIR",
            "labor_task_type": "maintenance",
            "labor_cost": Decimal("20.00"),
            "parts_cost": Decimal("35.50"),
            "total_amount": Decimal("55.50"),
            "status": "proposed",
            "parts": [{"name": "SSD 512GB", "quantity": 1,
                       "subtotal": Decimal("35.50")}],
        },
        "ticket_code": "TCK-CONTRACT",
        "ticket_status": "QUOTED",
        "quote_status": "proposed",
    }

    reply = DecentralizedPattern().to_reply(result)

    assert reply.pending_quote is True
    assert reply.quote is not None
    assert reply.quote.status == "proposed"
    assert reply.quote.total == Decimal("55.50")
    assert reply.ticket is not None
    assert reply.ticket.code == "TCK-CONTRACT"


@pytest.mark.parametrize(
    "action,expected_status",
    [("accept_quote", "confirmed"), ("reject_quote", "rejected")],
)
def test_quote_actions_have_the_same_chat_contract_for_every_pattern(
    pattern_settings, action, expected_status
):
    quote_data = {
        "quote_type": "REPAIR",
        "labor_task_type": "maintenance",
        "labor_cost": Decimal("20.00"),
        "parts_cost": Decimal("35.50"),
        "total_amount": Decimal("55.50"),
        "parts": [{"id": 7, "code": "SSD-512", "name": "SSD 512GB",
                   "quantity": 1, "unit_price": Decimal("35.50"),
                   "subtotal": Decimal("35.50"), "current_stock": 3}],
    }

    class Graph:
        def __init__(self, pattern_id):
            self.pattern_id = pattern_id

        def get_state(self, config):
            return SimpleNamespace(values={})

        def invoke(self, state, *, config, **_kwargs):
            del config
            turn = state["messages"][-1].content.casefold()
            if "rechazo" in turn or turn.strip() == "no":
                if self.pattern_id == "hierarchical":
                    return {"messages": [AIMessage(content="Rechazada")],
                            "outcome": "declined", "ticket_code": "TCK-TEST",
                            "ticket_status": "IN_DIAGNOSIS", "quote": quote_data}
                if self.pattern_id == "orchestrator":
                    return {"messages": [AIMessage(content="Rechazada")],
                            "ticket_code": "TCK-TEST", "ticket_status": "IN_DIAGNOSIS",
                            "ticket_cancelled": True, "total": quote_data["total_amount"],
                            "labor_cost": quote_data["labor_cost"],
                            "available_parts": quote_data["parts"]}
                return {"messages": [AIMessage(content="Rechazada")],
                        "quote_status": "rejected",
                        "ticket_code": "TCK-TEST", "ticket_status": "IN_DIAGNOSIS",
                        "quote": {**quote_data, "status": "rejected"}}
            if "confirmo" in turn:
                if self.pattern_id == "hierarchical":
                    return {"messages": [AIMessage(content="Aceptada")],
                            "outcome": "quoted", "ticket_status": "PAYMENT_PENDING",
                            "ticket_code": "TCK-TEST", "quote": quote_data}
                if self.pattern_id == "orchestrator":
                    return {"messages": [AIMessage(content="Aceptada")],
                            "quote_id": 93, "ticket_status": "PAYMENT_PENDING",
                            "ticket_code": "TCK-TEST", "total": quote_data["total_amount"],
                            "labor_cost": quote_data["labor_cost"],
                            "available_parts": quote_data["parts"]}
                return {"messages": [AIMessage(content="Aceptada")],
                        "quote_status": "confirmed", "ticket_status": "PAYMENT_PENDING",
                        "ticket_code": "TCK-TEST",
                        "quote": {**quote_data, "status": "confirmed"}}
            if self.pattern_id == "hierarchical":
                return {"messages": [AIMessage(content="Propuesta")],
                        "outcome": "awaiting_confirmation", "ticket_code": "TCK-TEST",
                        "ticket_status": "IN_DIAGNOSIS", "quote": quote_data}
            if self.pattern_id == "orchestrator":
                return {"messages": [AIMessage(content="Propuesta")],
                        "ticket_code": "TCK-TEST", "ticket_status": "IN_DIAGNOSIS",
                        "awaiting_ticket_confirmation": True,
                        "total": quote_data["total_amount"],
                        "labor_cost": quote_data["labor_cost"],
                        "available_parts": quote_data["parts"]}
            return {"messages": [AIMessage(content="Propuesta")],
                    "quote_status": "proposed",
                    "ticket_code": "TCK-TEST", "ticket_status": "IN_DIAGNOSIS",
                    "quote": {**quote_data, "status": "proposed"}}

    patterns = build_patterns(
        graph_factories={
            pattern_id: (lambda pattern_id=pattern_id: Graph(pattern_id))
            for pattern_id in {pattern.id for pattern in PATTERN_CLASSES}
        },
        settings_factory=lambda: pattern_settings,
        trace_context_factory=nullcontext,
    )

    class Limiter:
        def blocked(self, key): return False
        def fail(self, key): pass

    chat = SendChatMessage(patterns, ConversationRegistry(), Limiter())
    for pattern_id in sorted(patterns):
        proposal = chat.execute(
            customer_id=41, pattern=pattern_id, message="Necesito una cotización"
        )
        assert proposal.reply.pending_quote is True
        assert proposal.reply.ticket is not None
        assert proposal.reply.ticket.code == "TCK-TEST"
        assert proposal.reply.ticket.status != "PAYMENT_PENDING"
        confirmed = chat.execute(
            customer_id=41,
            pattern=pattern_id,
            action=action,
            conversation_id=proposal.conversation_id,
        )
        assert confirmed.reply.pending_quote is False
        assert confirmed.reply.quote is not None
        assert confirmed.reply.quote.status == expected_status
        assert confirmed.reply.quote.total == Decimal("55.50")
        assert confirmed.reply.ticket is not None
        assert confirmed.reply.ticket.code == "TCK-TEST"
