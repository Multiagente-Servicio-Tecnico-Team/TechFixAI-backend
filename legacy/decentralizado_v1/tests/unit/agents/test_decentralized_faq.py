from langchain_core.messages import AIMessage, HumanMessage
from types import SimpleNamespace

import app.agents.decentralized.support as support
import app.agents.decentralized.faq as faq
from app.agents.decentralized.graph import AGENT_NODES, graph, route_entry


def test_support_hands_payment_faq_to_the_dedicated_faq_agent():
    result = support.support_node({
        "messages": [HumanMessage(content="¿Qué tipo de pagos aceptan?")],
        "turn_start_index": 0,
    })

    assert result["current_agent"] == "soporte"
    assert result["messages"][0].tool_calls[0]["name"] == "transfer_to_faq"
    assert AGENT_NODES["faq"] is faq.faq_node


def test_faq_agent_uses_the_shared_canonical_retriever_and_answerer(monkeypatch):
    retrieved = {}

    def respond(_llm, question, context):
        retrieved.update(question=question, context=context)
        return "Aceptamos Yape, Plin, transferencia, tarjetas y efectivo en tienda."

    monkeypatch.setattr(
        faq._FAQ_RETRIEVER,
        "retrieve",
        lambda question, limit: "[Fuente FAQ: faq_servicio.md]\n## Pagos\nAceptamos Yape.",
    )
    monkeypatch.setattr(faq, "answer_faq", respond)
    result = faq.faq_node({
        "messages": [HumanMessage(content="¿Qué tipo de pagos aceptan?")],
    })

    assert result["current_agent"] == "faq"
    assert "Yape" in result["messages"][0].content
    assert retrieved["question"] == "¿Qué tipo de pagos aceptan?"
    assert "Yape" in retrieved["context"]


def test_general_support_path_can_inspect_tool_messages(monkeypatch):
    class Model:
        def invoke(self, _messages):
            return AIMessage(content="Hola, ¿en qué puedo ayudarte?")

    monkeypatch.setattr(support, "_resolve_support_llm", lambda: Model())
    result = support.support_node({
        "messages": [HumanMessage(content="Hola")],
        "turn_start_index": 0,
    })

    assert result["messages"][0].content == "Hola, ¿en qué puedo ayudarte?"


def test_completed_faq_turn_returns_to_support_for_the_next_question():
    assert route_entry({"current_agent": "faq"}) == "soporte"


def test_decentralized_graph_routes_to_faq_then_reclassifies_next_turn(monkeypatch):
    monkeypatch.setattr(
        faq._FAQ_RETRIEVER,
        "retrieve",
        lambda question, limit: "[Fuente FAQ: faq_servicio.md]\n## Pagos\nAceptamos Yape.",
    )
    monkeypatch.setattr(faq, "answer_faq", lambda _llm, _question, _context: "Aceptamos Yape.")
    first = graph.invoke({
        "messages": [HumanMessage(content="¿Qué tipo de pagos aceptan?")],
    })

    assert first["current_agent"] == "faq"
    assert first["handoff_history"] == [{"origin": "soporte", "destination": "faq"}]
    assert first["messages"][-1].content == "Aceptamos Yape."

    monkeypatch.setattr(
        support,
        "_resolve_support_llm",
        lambda: SimpleNamespace(invoke=lambda _messages: AIMessage(content="Hola, ¿en qué puedo ayudarte?")),
    )
    second = graph.invoke({
        **first,
        "messages": [*first["messages"], HumanMessage(content="Hola")],
    })

    assert second["current_agent"] == "soporte"
    assert second["messages"][-1].content == "Hola, ¿en qué puedo ayudarte?"
