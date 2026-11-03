from decimal import Decimal

from langchain_core.messages import HumanMessage

from app.agents.jerarquico.graph.builder import build_multiagent_graph
from app.agents.jerarquico.retriever import MarkdownKnowledgeRetriever
from app.settings import Settings


class _Repository:
    def __init__(self):
        self.calls = []

    def find_payment_id_by_code(self, customer_id, payment_code):
        self.calls.append(("lookup", customer_id, payment_code))
        return 17

    def request_refund(self, **values):
        self.calls.append(("request", values))
        return {"id": 3, "payment_id": 17, "ticket_id": 8, "status": "REQUESTED"}


class _NoCallModel:
    def with_structured_output(self, *_args, **_kwargs):
        raise AssertionError("Una intención de reembolso no debe depender del LLM")


def _settings():
    return Settings(
        groq_api_key="test-key",
        groq_model="test-model",
        database_url="postgresql+pg8000://localhost/test",
        langsmith_api_key=None,
        langsmith_tracing=False,
        langsmith_project="test",
        langsmith_hide_inputs=True,
        langsmith_hide_outputs=True,
        labor_maintenance_price=Decimal("35.00"),
        labor_diagnosis_price=Decimal("50.00"),
    )


def test_hierarchical_refund_flow_collects_details_then_registers_pending_only():
    repository = _Repository()
    graph = build_multiagent_graph(
        settings=_settings(),
        repository=repository,
        model=_NoCallModel(),
        retriever=MarkdownKnowledgeRetriever(documents=()),
    )
    config = {"configurable": {"thread_id": "refund-contract"}}

    first = graph.invoke(
        {"customer_id": 41, "messages": [HumanMessage(content="Quiero un reembolso")]},
        config=config,
    )
    assert first["awaiting_refund_details"] is True
    assert repository.calls == []

    second = graph.invoke(
        {"messages": [HumanMessage(content="PAY-ABC123; importe: S/ 25.50; motivo: producto defectuoso")]},
        config=config,
    )
    assert second["refund_status"] == "REQUESTED"
    assert second["awaiting_refund_details"] is False
    assert "revisión manual" in second["messages"][-1].content.casefold()
    assert repository.calls == [
        ("lookup", 41, "PAY-ABC123"),
        ("request", {
            "customer_id": 41,
            "payment_id": 17,
            "amount": Decimal("25.50"),
            "reason": "producto defectuoso",
        }),
    ]


def test_hierarchical_supplier_request_returns_unavailable_without_write():
    repository = _Repository()
    graph = build_multiagent_graph(
        settings=_settings(), repository=repository, model=_NoCallModel(),
        retriever=MarkdownKnowledgeRetriever(documents=()),
    )
    result = graph.invoke(
        {"customer_id": 41, "messages": [HumanMessage(content="¿Pueden comprar el repuesto al proveedor?")]},
        config={"configurable": {"thread_id": "hierarchical-procurement"}},
    )

    assert result["outcome"] == "procurement_unavailable"
    assert "no se creó una orden" in result["messages"][-1].content.casefold()
    assert repository.calls == []
