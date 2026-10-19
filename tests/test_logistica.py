"""Deterministic logistics decisions and tools, external SQL mocked."""
from unittest.mock import MagicMock
import pytest
from langchain_core.messages import HumanMessage
from app.agents.decentralized.logistica import logistica_node, collect_logistics, logistica_tools
from app.agents.decentralized.tools.logistica_tools import transferir_a_logistica
from app.agents.decentralized.handoffs import HANDOFF_TOOLS
from app.database.decentralized_repository import RetryConflict


def setup(kind="REPAIR", logistics=None, text=""):
    repo = MagicMock()
    repo.get_logistics_context.return_value = dict(id=1, customer_id=10, request_type=kind)
    state = dict(customer_id=10, ticket_id=1, request_revision=0,
                 logistics=logistics or {}, messages=[HumanMessage(content=text)])
    return repo, state


def run(repo, state):
    return logistica_node(state, repository=repo, authenticated_customer_id=10)


def test_presencial_no_address_requested_or_persisted():
    repo, state = setup(text="Prefiero retiro presencial")
    result = run(repo, state)
    assert result["pending_logistics_operation"]["payload"]["shipping_address"] is None
    assert "dirección" not in result["messages"][0].content
    repo.create_initial_logistics.assert_not_called()


def test_courier_sale_complete_explicit_data():
    repo, state = setup("SALE", text="courier: Empresa de prueba; dirección: Calle de prueba; destinatario: Persona de prueba; teléfono: 000000000")
    result = run(repo, state)
    assert result["pending_logistics_operation"]["payload"]["shipping_address"] == "Calle de prueba"
    assert result["pending_logistics_operation"]["payload"]["courier_company"] == "Empresa de prueba"
    assert run(repo, {**state, **result})["pending_logistics_operation"] == result["pending_logistics_operation"]


def test_courier_repair_only_requires_carrier():
    repo, state = setup(text="courier: Empresa de prueba")
    result = run(repo, state)
    payload = result["pending_logistics_operation"]["payload"]
    assert payload["shipping_address"] is None and payload["recipient_phone"] is None


def test_courier_missing_data_asks_only_missing_fields():
    repo, state = setup("PC_BUILD", dict(mode="COURIER_SHIPMENT", courier_company="Empresa de prueba"))
    result = run(repo, state)
    assert "pending_logistics_operation" not in result
    assert "dirección" in result["messages"][0].content
    assert "empresa de courier" not in result["messages"][0].content


@pytest.mark.parametrize("cause", ["identity", "no_payment", "no_claim", "storage", "invalid_mode", "tracking", "stale"])
def test_rejects_unverified_state_and_no_write(cause):
    repo, state = setup(logistics=dict(mode="PHYSICAL_STORE"))
    if cause == "identity": state["customer_id"] = 99
    if cause in {"no_payment", "no_claim"}: repo.get_logistics_context.side_effect = ValueError("Unmet precondition")
    if cause == "storage": repo.get_logistics_context.side_effect = RuntimeError("Sensitive details")
    if cause == "invalid_mode": state["logistics"]["mode"] = "FLY"
    if cause == "tracking": state["logistics"]["tracking_number"] = "Invented"
    if cause == "stale":
        prepared = run(repo, state)
        state.update(prepared)
        state["request_revision"] = 1
    if cause in {"identity", "stale"}:
        with pytest.raises(RetryConflict): run(repo, state)
        repo.create_initial_logistics.assert_not_called()
        return
    result = run(repo, state)
    assert "pending_logistics_operation" not in result
    assert "Sensitive details" not in result["messages"][0].content
    repo.create_initial_logistics.assert_not_called()


def test_no_backend_identity_no_preparation():
    repo, state = setup()
    assert "pending_logistics_operation" not in logistica_node(state, repository=repo)
    repo.get_logistics_context.assert_not_called()


def test_tools_contract_and_no_guarantee_agent():
    for tool in [transferir_a_logistica, *logistica_tools]:
        assert tool.name in HANDOFF_TOOLS
        with pytest.raises(ValueError):
            tool.invoke({("reason" if tool.name.startswith("transfer_to_") else "motivo"):" "})
        assert "TRANSFERIR" in tool.invoke({("reason" if tool.name.startswith("transfer_to_") else "motivo"):"Coordinación requerida"})
    assert not any(tool.name == "transferir_a_garantia" for tool in logistica_tools)


@pytest.mark.parametrize("text,mode", [("No quiero retiro presencial, prefiero courier", "COURIER_SHIPMENT"),
    ("No quiero courier, prefiero retiro presencial", "PHYSICAL_STORE"),
    ("Retiro presencial o courier", None)])
def test_mode_negations_and_ambiguous_choice(text, mode):
    _, state = setup(text=text)
    assert collect_logistics(state).get("mode") == mode


def test_changed_pending_content_requires_explicit_reconciliation():
    repo, state = setup(text="Prefiero retiro presencial")
    state.update(run(repo,state))
    state["messages"] = [HumanMessage(content="courier: Otra empresa")]
    with pytest.raises(RetryConflict):
        run(repo,state)
    assert state["pending_logistics_operation"]["payload"]["mode"] == "PHYSICAL_STORE"
    repo.create_initial_logistics.assert_not_called()
