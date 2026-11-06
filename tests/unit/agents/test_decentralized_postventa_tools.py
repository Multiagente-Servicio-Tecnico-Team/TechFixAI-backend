"""Post-sale responsibilities belong to the original specialized roles."""
from app.agents.decentralized.billing import billing_node
from app.agents.decentralized.tools.billing_tools import consultar_capacidades_financieras
from app.agents.decentralized.warranty import warranty_node


def test_billing_keeps_payment_writes_disabled_and_never_confirms_refund():
    capabilities = consultar_capacidades_financieras.invoke({})
    assert capabilities["payment_write_enabled"] is False
    assert capabilities["refund_write_enabled"] is False
    response = billing_node({"intent": "REFUND"})
    assert "no se ha registrado" in response["messages"][0].content.casefold()


def test_warranty_requires_an_authenticated_lookup_instead_of_claiming_coverage():
    response = warranty_node({})
    assert response["current_agent"] == "garantia"
    assert not response.get("pending_warranty_operation")
    assert "autenticada" in response["messages"][0].content
