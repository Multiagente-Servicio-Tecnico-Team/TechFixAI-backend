import pytest
from langchain_core.messages import HumanMessage

from app.agents.jerarquico.supervisor import make_customer_care_supervisor


class NoCallModel:
    def with_structured_output(self, *_args, **_kwargs):
        raise AssertionError("Una solicitud directa a proveedores no requiere clasificador LLM")


@pytest.mark.parametrize("pattern_id", ["hierarchical", "orchestrator", "decentralized"])
def test_customer_patterns_do_not_register_supplier_purchase_agent(pattern_id, pattern_settings):
    if pattern_id == "hierarchical":
        from app.agents.jerarquico.graph.builder import build_multiagent_graph as build
    elif pattern_id == "orchestrator":
        from app.agents.orquestador import build_graph as build
    else:
        from app.agents.decentralized.network import build_graph as build

    graph = build(settings=pattern_settings, repository=object(), model=NoCallModel())
    assert "purchasing_agent" not in graph.get_graph().nodes


def test_explicit_supplier_request_explains_customer_chat_scope_without_order():
    result = make_customer_care_supervisor(NoCallModel(), object())({
        "customer_id": 41,
        "messages": [HumanMessage(content="¿Pueden comprar al proveedor un repuesto agotado?")],
    })

    assert result["route"] == "clarification"
    assert result["outcome"] == "supplier_procurement_unavailable"
    response = result["messages"][-1].content.casefold()
    assert "módulo administrativo" in response
    assert "alternativas" in response and "catálogo" in response
    assert "no se creó una compra" in response
