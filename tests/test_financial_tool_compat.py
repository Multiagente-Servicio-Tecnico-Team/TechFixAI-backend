from copy import deepcopy
import json
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver

from app.agents.decentralized.facturacion import facturacion_tools
from app.agents.decentralized.tools.facturacion_tools import (
    consultar_capacidades_financieras,
    get_financial_capabilities,
)
from test_software_e2e import network


NAMES = ["get_financial_capabilities", "consultar_capacidades_financieras"]
EXPECTED = dict(payment_write_enabled=False, fiscal_integration_available=False,
                payment_reconciliation_available=False, refund_write_enabled=False)


def test_active_registry_has_only_new_capability_name():
    assert [item.name for item in facturacion_tools] == [
        "transfer_to_support", "transfer_to_sales", "get_financial_capabilities",
        "transfer_to_logistics",
    ]


@pytest.mark.parametrize("tool", [consultar_capacidades_financieras, get_financial_capabilities])
def test_direct_invocation_schema_and_no_shared_result(tool):
    schema = tool.args_schema.model_json_schema()
    assert schema["properties"] == {}
    assert schema.get("required", []) == []
    assert tool.args == {}
    assert tool.invoke({}) == EXPECTED
    changed = tool.invoke({})
    changed["payment_write_enabled"] = True
    assert tool.invoke({}) == EXPECTED


def test_alias_preserves_implementation_description_and_legacy_name():
    assert consultar_capacidades_financieras.name == NAMES[1]
    assert get_financial_capabilities.name == NAMES[0]
    assert get_financial_capabilities.func is consultar_capacidades_financieras.func
    assert get_financial_capabilities.description == consultar_capacidades_financieras.description
    assert get_financial_capabilities.args_schema is consultar_capacidades_financieras.args_schema


def test_compiled_registry_contains_each_variant_once(network):
    module, _ = network
    node = module.build_graph().get_graph().nodes["facturacion_tools"].data
    assert set(node.tools_by_name) == {item.name for item in facturacion_tools} | {NAMES[1], "transferir_a_soporte", "transferir_a_ventas", "transferir_a_logistica"}


@pytest.mark.parametrize("names", [[NAMES[0]], [NAMES[1]], NAMES, [NAMES[1], NAMES[1]]])
@pytest.mark.parametrize("resume", [False, True])
def test_real_toolnode_and_checkpoint_preserve_calls(network, monkeypatch, names, resume):
    module, _ = network
    repo = MagicMock()
    calls = [dict(name=name, args={}, id=f"capability-{i}") for i, name in enumerate(names)]
    original = AIMessage(content="", tool_calls=calls, id="capability-batch")
    before = deepcopy(original)
    state = dict(messages=[HumanMessage(content="Capacidades", id="user"), original],
                 current_agent="facturacion", handoff_history=[])

    def financial_node(state, **kwargs):
        if isinstance(state["messages"][-1], ToolMessage):
            return {"current_agent": "facturacion", "messages": [AIMessage(content="Fin")]}
        return {"current_agent": "facturacion", "messages": [original]}

    monkeypatch.setitem(module.AGENT_NODES, "facturacion", financial_node)
    monkeypatch.setattr(module, "billing_node", financial_node)
    saver = MemorySaver()
    graph = module.build_graph(checkpointer=saver, financial_repository=repo)
    config = {"configurable": {"thread_id": "capabilities"}}
    if resume:
        graph.update_state(config, state, as_node="facturacion")
        graph = module.build_graph(checkpointer=saver, financial_repository=repo)
        result = graph.invoke(None, config)
    else:
        result = graph.invoke({"messages": state["messages"][:1], "current_agent": "facturacion"}, config)
    outputs = [item for item in result["messages"] if isinstance(item, ToolMessage)]
    assert [(item.name, item.tool_call_id) for item in outputs] == [
        (name, call["id"]) for name, call in zip(names, calls)
    ]
    assert all(item.status != "error" for item in outputs)
    assert all(json.loads(item.content) == EXPECTED for item in outputs)
    assert original == before
    assert result["handoff_history"] == []
    assert repo.mock_calls == []


def test_actual_financial_agent_remains_deterministic_and_read_only(network):
    module, _ = network
    result = module.build_graph().invoke(dict(
        messages=[HumanMessage(content="Confirma mi pago")], current_agent="facturacion"))
    assert result["current_agent"] == "facturacion"
    assert not any(isinstance(item, ToolMessage) for item in result["messages"])
    assert "payment_id" not in result
