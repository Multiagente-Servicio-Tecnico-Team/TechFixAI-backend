from decimal import Decimal
from unittest.mock import MagicMock
import pytest
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from test_software_e2e import network


def configured(network, saver):
    module, _ = network
    repo = MagicMock()
    repo.get_ticket.return_value = dict(id=1, customer_id=10, status="QUOTED")
    repo.get_quote.return_value = dict(id=2, ticket_id=1, status="ACCEPTED", total_amount=Decimal("1.00"))
    return module.build_graph(checkpointer=saver, financial_repository=repo), repo


def initial():
    return dict(messages=[HumanMessage(content="Preparar pago")], current_agent="facturacion",
                customer_id=10, ticket_id=1, quote_id=2, request_revision=0)


def test_prepared_checkpoint_then_rebuilt_graph_resumes_without_reconstruction(network):
    saver = MemorySaver()
    graph, repo = configured(network, saver)
    config = {"configurable": {"thread_id": "payment-recovery"}}
    context = {"authenticated_customer_id": 10}
    graph.invoke(initial(), config, context=context, durability="sync")
    saved = graph.get_state(config)
    assert saved.next == ("ejecutar_pago",)
    pending = saved.values["pending_payment_operation"]
    recovered, new_repo = configured(network, saver)
    result = recovered.invoke(None, config, context=context, durability="sync")
    assert result["pending_payment_operation"] == pending
    new_repo.get_quote.assert_not_called()
    repo.create_pending_payment.assert_not_called()
    new_repo.create_pending_payment.assert_not_called()
    assert "payment_id" not in result


def test_failure_at_execution_keeps_original_operation(network):
    saver = MemorySaver()
    graph, repo = configured(network, saver)
    config = {"configurable": {"thread_id": "payment-failure"}}
    graph.invoke(initial(), config, context={"authenticated_customer_id":10}, durability="sync")
    before = graph.get_state(config).values["pending_payment_operation"]
    with pytest.raises(ValueError):
        graph.invoke(None, config, context={"authenticated_customer_id":99}, durability="sync")
    assert graph.get_state(config).values["pending_payment_operation"] == before
    result = graph.invoke(None, config, context={"authenticated_customer_id":10}, durability="sync")
    assert result["pending_payment_operation"] == before
    repo.create_pending_payment.assert_not_called()


def test_state_identity_does_not_authorize_preparation(network):
    graph, repo = configured(network, MemorySaver())
    result = graph.invoke(initial(), {"configurable":{"thread_id":"untrusted"}}, durability="sync")
    assert "pending_payment_operation" not in result
    repo.get_quote.assert_not_called()


def test_financial_repository_requires_checkpointer(network):
    with pytest.raises(ValueError):
        network[0].build_graph(financial_repository=MagicMock())
