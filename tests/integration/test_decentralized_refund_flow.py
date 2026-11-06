"""Refunds do not become a tenth role or acquire new write permissions."""
from app.agents.decentralized.graph import AGENT_NODES
from app.agents.decentralized.billing import billing_node
from app.agents.decentralized.tools.purchasing_tools import consultar_fuentes_abastecimiento


def test_refund_is_not_a_tenth_functional_role():
    assert len(AGENT_NODES) == 9 and "reembolsos" not in AGENT_NODES
    result = billing_node({"intent": "REFUND"})
    assert result["current_agent"] == "facturacion"
    assert "no se ha registrado" in result["messages"][0].content.casefold()


def test_purchasing_keeps_the_original_unavailable_sourcing_capability():
    assert consultar_fuentes_abastecimiento.invoke({})["integration_available"] is False
