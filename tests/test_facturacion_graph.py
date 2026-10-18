"""Compiled real network; external models/RAG mocked by the existing fixture."""
from unittest.mock import MagicMock
import pytest
from langchain_core.messages import HumanMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver
from test_software_e2e import network, call


def test_facturacion_registered_and_pending_preserved(network):
    graph_module, controls = network
    pending = dict(request_revision=0, payload=dict(customer_id=1, ticket_id=2, quote_id=3, payment_code="PAY-TEST"))
    result = graph_module.build_graph().invoke(dict(messages=[HumanMessage(content="Ya pagué")],
        current_agent="facturacion", customer_id=1, pending_payment_operation=pending))
    assert result["current_agent"] == "facturacion"
    assert result["pending_payment_operation"] == pending
    assert "payment_id" not in result
    assert "logistica" in graph_module.AGENT_NODES
    assert "garantia" in graph_module.AGENT_NODES


@pytest.mark.parametrize("origin", ["soporte", "ventas"])
def test_real_incoming_handoff_and_no_financial_writes(network, monkeypatch, origin):
    graph_module, controls = network
    from app.database.decentralized_repository import DecentralizedRepository
    write = MagicMock(side_effect=AssertionError("Financial writes forbidden"))
    monkeypatch.setattr(DecentralizedRepository, "create_pending_payment", write)
    controls["handlers"][origin] = lambda messages: call("transferir_a_facturacion", motivo="Consultar operación financiera")
    result = graph_module.build_graph().invoke(dict(messages=[HumanMessage(content="Consulta financiera")], current_agent=origin))
    assert result["current_agent"] == "facturacion"
    assert result["handoff_history"] == [{"origin": origin, "destination": "facturacion"}]
    assert any(isinstance(message, ToolMessage) and message.name == "transferir_a_facturacion" for message in result["messages"])
    write.assert_not_called()


@pytest.mark.parametrize("destination", ["soporte", "ventas"])
def test_real_outgoing_tools_and_audit(network, monkeypatch, destination):
    graph_module, controls = network
    def financial_node(state):
        return {"current_agent": "facturacion", "messages": [call(f"transferir_a_{destination}", motivo="Revisión requerida")]}
    monkeypatch.setitem(graph_module.AGENT_NODES, "facturacion", financial_node)
    result = graph_module.build_graph().invoke(dict(messages=[HumanMessage(content="Consulta general")], current_agent="facturacion"))
    assert result["handoff_history"][0] == {"origin": "facturacion", "destination": destination}
    assert result["handoff_records"][0]["reason"] == "Revisión requerida"


def test_checkpointer_continuity_financial_state(network):
    graph_module, _ = network
    graph = graph_module.build_graph(checkpointer=MemorySaver())
    config = {"configurable": {"thread_id": "finance-test"}}
    first = graph.invoke(dict(messages=[HumanMessage(content="Consulta")], current_agent="facturacion"), config)
    second = graph.invoke(dict(messages=[HumanMessage(content="Continuar")]), config)
    assert second["current_agent"] == "facturacion"
    assert len(second["messages"]) > len(first["messages"])
