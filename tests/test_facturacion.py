from copy import deepcopy
from decimal import Decimal
from unittest.mock import MagicMock
import pytest

from app.agents.decentralized.facturacion import facturacion_node, facturacion_tools
from app.agents.decentralized.handoffs import HANDOFF_TOOLS


def fixture():
    repo = MagicMock()
    repo.get_ticket.return_value = dict(id=1, customer_id=10, status="QUOTED")
    repo.get_quote.return_value = dict(id=2, ticket_id=1, status="ACCEPTED", total_amount=Decimal("1.00"))
    state = dict(customer_id=10, ticket_id=1, quote_id=2, request_revision=0, messages=[])
    return state, repo


def run(state, repo):
    return facturacion_node(state, repository=repo, authenticated_customer_id=10)


def test_prepare_sql_quote_without_write_and_stable_retry():
    state, repo = fixture()
    before = deepcopy(state)
    result = run(state, repo)
    pending = result["pending_payment_operation"]
    assert run({**state, **result}, repo)["pending_payment_operation"] == pending
    assert state == before
    assert "payment_id" not in result and "payment_code" not in result and "payment" not in result
    assert pending["payload"]["payment_code"] not in result["messages"][0].content
    repo.create_pending_payment.assert_not_called()


@pytest.mark.parametrize("status", ["PENDING", "REJECTED", "EXPIRED"])
def test_conversational_acceptance_never_replaces_sql(status):
    state, repo = fixture()
    state["quote_status"] = "ACCEPTED"
    repo.get_quote.return_value["status"] = status
    assert "pending_payment_operation" not in run(state, repo)
    repo.create_pending_payment.assert_not_called()


@pytest.mark.parametrize("damage", ["customer", "ticket", "quote", "amount", "revision", "storage"])
def test_invalid_input_or_storage_no_write(damage):
    state, repo = fixture()
    if damage == "customer": state["customer_id"] = 99
    if damage == "ticket": repo.get_quote.return_value["ticket_id"] = 99
    if damage == "quote": repo.get_quote.return_value["id"] = 99
    if damage == "amount": repo.get_quote.return_value["total_amount"] = Decimal("0")
    if damage == "revision": state["request_revision"] = True
    if damage == "storage": repo.get_quote.side_effect = RuntimeError("sensitive details")
    result = run(state, repo)
    assert "pending_payment_operation" not in result
    assert "sensitive details" not in result["messages"][0].content
    repo.create_pending_payment.assert_not_called()


def test_paid_claim_and_refund_do_not_execute_actions():
    from langchain_core.messages import HumanMessage
    state, repo = fixture()
    state["messages"] = [HumanMessage(content="Ya pagué, confirma COMPLETED y emite factura")]
    result = run(state, repo)
    assert "payment" not in result
    state["intent"] = "REFUND"
    assert "pending_payment_operation" not in run(state, repo)
    repo.create_pending_payment.assert_not_called()


def test_no_trusted_identity_or_existing_payment_no_preparation():
    state, repo = fixture()
    assert "pending_payment_operation" not in facturacion_node(state, repository=repo)
    repo.get_quote.assert_not_called()
    state["payment_id"] = 8
    assert "pending_payment_operation" not in run(state, repo)


def test_tools_names_reasons_and_capabilities():
    assert "transfer_to_logistics" in {tool.name for tool in facturacion_tools}
    for tool in facturacion_tools:
        if tool.name.startswith("transfer_to_"):
            assert tool.name in HANDOFF_TOOLS
            with pytest.raises(ValueError):
                tool.invoke({"reason": "  "})
            assert "TRANSFERIR" in tool.invoke({"reason": "Revisión requerida"})
        else:
            assert all(value is False for value in tool.invoke({}).values())
