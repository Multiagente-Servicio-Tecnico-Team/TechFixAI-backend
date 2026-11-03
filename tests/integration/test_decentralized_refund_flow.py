from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver

from app.agents.decentralized.graph import build_graph


def test_decentralized_refund_handoff_asks_for_details_without_payment_side_effect():
    graph = build_graph(checkpointer=MemorySaver())
    result = graph.invoke(
        {
            "customer_id": 41,
            "conversation_id": "decentralized-refund",
            "messages": [HumanMessage(content="Quiero solicitar un reembolso")],
        },
        config={"configurable": {"thread_id": "decentralized-refund"}},
    )

    assert result["current_agent"] == "reembolsos"
    assert result["awaiting_refund_details"] is True
    assert "PAY-" in result["messages"][-1].content
    assert not result.get("refund_id")


def test_decentralized_supplier_purchase_handoff_returns_unavailable_without_order():
    graph = build_graph(checkpointer=MemorySaver())
    result = graph.invoke(
        {
            "customer_id": 41,
            "conversation_id": "decentralized-procurement",
            "messages": [HumanMessage(content="¿Pueden comprar el repuesto al proveedor?")],
        },
        config={"configurable": {"thread_id": "decentralized-procurement"}},
    )

    assert result.get("outcome") == "procurement_unavailable", result
    assert "precio" in result["messages"][-1].content.casefold()
    assert "no se creó una orden" in result["messages"][-1].content.casefold()
    assert not result.get("purchase_order_id")
