import pytest

from app.agents.jerarquico.agents.procurement import purchasing_agent
from app.agents.orquestador.agentes.compras import procurement_node as orchestrator_procurement
from app.agents.decentralized.compras import procurement_node as decentralized_procurement
from app.agents.jerarquico.supervisor import make_customer_care_supervisor
from langchain_core.messages import HumanMessage


@pytest.mark.parametrize(
    "agent",
    [purchasing_agent, orchestrator_procurement, decentralized_procurement],
    ids=["hierarchical", "orchestrator", "decentralized"],
)
def test_supplier_purchase_is_unavailable_without_price_order_or_reservation(agent):
    result = agent({"messages": []})

    assert result["outcome"] == "procurement_unavailable"
    response = result["messages"][-1].content.casefold()
    assert "no puedo confirmar" in response
    assert "precio" in response and "plazo" in response
    assert "reservó inventario" in response
    assert "no se creó una orden" in response or "no se reservó inventario" in response
    assert not any(
        key in result
        for key in ("purchase_order", "purchase_order_id", "supplier", "lead_time")
    )


def test_hierarchical_supervisor_routes_supplier_intent_without_model_or_write():
    class NoCallModel:
        def with_structured_output(self, *_args, **_kwargs):
            raise AssertionError("La petición de compra a proveedor tiene ruta determinista")

    result = make_customer_care_supervisor(NoCallModel(), object())({
        "customer_id": 41,
        "messages": [HumanMessage(content="¿Pueden comprar al proveedor un repuesto agotado?")],
    })

    assert result["route"] == "supplier_procurement"
