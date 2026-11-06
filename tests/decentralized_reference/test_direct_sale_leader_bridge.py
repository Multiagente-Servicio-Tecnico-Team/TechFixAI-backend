from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from contextlib import nullcontext
from types import SimpleNamespace

import pytest

from app.agents.decentralized.workflow.graph import build_graph
from app.adapters.patterns.decentralized import build_invoker
from app.application.errors import ConversationActionError


def test_direct_sale_reuses_leader_sales_without_creating_a_ticket(monkeypatch):
    from app.agents.decentralized import ventas

    seen = []

    def leader_sales(state):
        seen.append((state["customer_id"], state["commercial_customer_id"], state.get("ticket_id")))
        return {"current_agent": "ventas", "messages": [AIMessage(content="Venta directa pendiente.")]}

    monkeypatch.setattr(ventas, "ventas_node", leader_sales)
    graph = build_graph(MemorySaver(), financial_repository=object(),
                        ticket_writes=True, quote_writes=True)
    result = graph.invoke(
        {"messages": [HumanMessage(content="Quiero comprar un SSD")],
         "customer_id": 7, "commercial_customer_id": 42},
        config={"configurable": {"thread_id": "venta-directa-lider"}},
        context={"authenticated_customer_id": 7, "commercial_customer_id": 42},
    )

    assert seen == [(42, 42, None)]
    assert result["customer_id"] == 7
    assert result.get("ticket_id") is None
    assert result["request_type"] == "SALE"
    assert result["quote_type"] == "DIRECT_SALE"
    assert result["quote_task_type"] == "sale"


class DirectSaleGraph:
    def __init__(self, owner=7, commercial=42):
        self.saved = {"customer_id": owner, "commercial_customer_id": commercial,
                      "quote_type": "DIRECT_SALE", "ticket_id": None,
                      "quote_id": 19, "quote_status": "proposed"}
        self.calls = []

    def get_state(self, config):
        return SimpleNamespace(values=self.saved)

    def invoke(self, state, *, config, context, durability):
        self.calls.append((state, context, durability))
        return {"quote_status": "confirmed"}


def test_direct_sale_action_uses_authenticated_owner_and_explicit_decision():
    graph = DirectSaleGraph()
    invoke = build_invoker(lambda _pattern: graph, {"decentralized": lambda: graph}, None,
                           nullcontext, lambda: None,
                           lambda cid: {"configurable": {"thread_id": cid}})
    result = invoke("decentralized", "conversation", SimpleNamespace(id=7, commercial_customer_id=42),
                    "", quote_action="accept_quote")

    assert result["quote_status"] == "confirmed"
    state, context, durability = graph.calls[0]
    assert state["messages"][-1].content == "sí"
    assert state["customer_id"] == context["authenticated_customer_id"] == 7
    assert state["commercial_customer_id"] == context["commercial_customer_id"] == 42
    assert durability == "sync"


def test_direct_sale_action_rejects_another_customer_without_writing():
    graph = DirectSaleGraph()
    invoke = build_invoker(lambda _pattern: graph, {"decentralized": lambda: graph}, None,
                           nullcontext, lambda: None,
                           lambda cid: {"configurable": {"thread_id": cid}})

    with pytest.raises(ConversationActionError):
        invoke("decentralized", "conversation", SimpleNamespace(id=8, commercial_customer_id=43),
               "", quote_action="accept_quote")
    assert graph.calls == []


def test_leader_quote_tool_uses_commercial_profile_for_catalog(monkeypatch):
    from app.agents.decentralized.tools import ventas_tools as leader_sales_tools
    from app.adapters.tools.quotes import QuotePartInput

    recorded = {}

    class Calculator:
        def invoke(self, payload):
            recorded["parts"] = payload["parts"]
            return {"total_amount": "25.00"}

    monkeypatch.setattr(leader_sales_tools, "make_quote_calculation_tool",
                        lambda _catalog, **kwargs: recorded.update(kwargs) or Calculator())
    monkeypatch.setattr(leader_sales_tools, "load_settings",
                        lambda: SimpleNamespace(labor_price_for=lambda _kind: 0))

    result = leader_sales_tools.generar_cotizacion.func(
        parts=[QuotePartInput(code="SSD-1", quantity=1)],
        state={"customer_id": 7, "commercial_customer_id": 42,
               "conversation_id": "conversation", "quote_type": "DIRECT_SALE",
               "quote_task_type": "sale"},
    )

    assert result["total_amount"] == "25.00"
    assert recorded["customer_context"].customer_id == 42
    assert recorded["parts"] == [{"code": "SSD-1", "quantity": 1}]


def test_direct_sale_chat_action_reaches_the_same_leader_role(monkeypatch):
    from app.agents.decentralized import ventas
    from app.agents.decentralized.policies.policy import latest_user_message

    seen = []

    def leader_sales(state):
        seen.append((state["customer_id"], state.get("ticket_id"), latest_user_message(state)))
        if state.get("quote_status") == "proposed":
            return {"current_agent": "ventas", "quote_status": "confirmed",
                    "quote": {**state["quote"], "status": "confirmed"},
                    "quote_id": 19, "messages": [AIMessage(content="Venta aceptada.")]}
        return {"current_agent": "ventas", "quote_status": "proposed", "quote_id": 19,
                "quote": {"quote_type": "DIRECT_SALE", "total_amount": "25.00",
                          "parts": [], "status": "proposed"},
                "messages": [AIMessage(content="Cotización pendiente.")]}

    monkeypatch.setattr(ventas, "ventas_node", leader_sales)
    graph = build_graph(MemorySaver(), financial_repository=object(),
                        ticket_writes=True, quote_writes=True)
    invoke = build_invoker(lambda _pattern: graph, None, object(), nullcontext,
                           lambda: None, lambda cid: {"configurable": {"thread_id": cid}})
    customer = SimpleNamespace(id=7, commercial_customer_id=42)
    proposed = invoke("decentralized", "direct-sale-conversation", customer, "Quiero comprar un SSD")
    confirmed = invoke("decentralized", "direct-sale-conversation", customer, "",
                       quote_action="accept_quote")

    assert proposed["quote_status"] == "proposed"
    assert confirmed["quote_status"] == "confirmed"
    assert confirmed["customer_id"] == 7
    assert confirmed.get("ticket_id") is None
    assert seen == [(42, None, "Quiero comprar un SSD"), (42, None, "sí")]
