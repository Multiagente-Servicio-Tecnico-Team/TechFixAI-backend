from copy import deepcopy
import json

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver
from pydantic import ValidationError

from app.agents.decentralized.tools.tecnico_tools import diagnose_issue, diagnosticar_problema
from app.agents.decentralized.tools.compras_tools import (
    get_sourcing_capabilities, consultar_fuentes_abastecimiento,
)
from test_software_e2e import network
from test_compras import value


@pytest.mark.parametrize("symptom", ["no enciende", "se apaga", "pantalla azul", "esta lento", "desconocido", "  NO ENCIENDE  "])
def test_diagnostic_variants_have_identical_results(symptom):
    assert diagnose_issue.invoke({"symptom": symptom}) == diagnosticar_problema.invoke({"sintoma": symptom})


@pytest.mark.parametrize("tool,parameter", [(diagnose_issue, "symptom"), (diagnosticar_problema, "sintoma")])
def test_diagnostic_public_schemas_and_required_argument(tool, parameter):
    schema = tool.args_schema.model_json_schema()
    assert set(schema["properties"]) == {parameter}
    assert schema["properties"][parameter]["type"] == "string"
    assert schema["required"] == [parameter]
    with pytest.raises(ValidationError):
        tool.invoke({})
    with pytest.raises(ValidationError):
        tool.invoke({parameter: None})
    with pytest.raises(ValidationError):
        tool.invoke({"sintoma" if parameter == "symptom" else "symptom": "no enciende"})


@pytest.mark.parametrize("tool", [get_sourcing_capabilities, consultar_fuentes_abastecimiento])
def test_sourcing_schema_result_and_fresh_containers(tool):
    assert tool.args_schema.model_json_schema()["properties"] == {}
    result = tool.invoke({})
    assert result == consultar_fuentes_abastecimiento.invoke({})
    assert result["integration_available"] is False
    result["missing_fields"].clear()
    assert tool.invoke({})["missing_fields"]


def test_exact_active_and_execution_registries(network):
    module, _ = network
    active = {"tecnico": "diagnose_issue", "compras": "get_sourcing_capabilities"}
    legacy = {"tecnico": "diagnosticar_problema", "compras": "consultar_fuentes_abastecimiento"}
    graph = module.build_graph().get_graph()
    for role, name in active.items():
        tools = getattr(module, f"{role}_tools")
        names = [tool.name for tool in tools]
        assert names.count(name) == 1 and legacy[role] not in names
        registered = graph.nodes[f"{role}_tools"].data.tools_by_name
        handoff_legacy = {"transferir_a_soporte", "transferir_a_software", "transferir_a_ventas", "transferir_a_almacen", "transferir_a_logistica"} if role == "tecnico" else {"transferir_a_ventas"}
        assert set(registered) == set(names) | {legacy[role]} | handoff_legacy


@pytest.mark.parametrize("resume", [False, True])
@pytest.mark.parametrize("style", ["english", "legacy", "batch"])
def test_diagnosis_real_graph_messages_and_resume(network, monkeypatch, resume, style):
    module, controls = network
    variants = {
        "english": [dict(name="diagnose_issue", args={"symptom": "no enciende"}, id="new")],
        "legacy": [dict(name="diagnosticar_problema", args={"sintoma": "no enciende"}, id="old")],
    }
    calls = variants[style] if style != "batch" else variants["english"] + variants["legacy"]
    event = AIMessage(content="", tool_calls=calls, id="diagnosis-event")
    original = deepcopy(event)
    controls["handlers"]["tecnico"] = lambda messages: (
        AIMessage(content="Fin") if isinstance(messages[-1], ToolMessage) else event)
    saver = MemorySaver()
    config = {"configurable": {"thread_id": "diagnostic-compat"}}
    graph = module.build_graph(checkpointer=saver)
    if resume:
        graph.update_state(config, dict(messages=[HumanMessage(content="Mi PC no enciende", id="user"), event],
            current_agent="tecnico", handoff_history=[]), as_node="tecnico")
        graph = module.build_graph(checkpointer=saver)
        result = graph.invoke(None, config)
    else:
        result = graph.invoke(dict(messages=[HumanMessage(content="Mi PC no enciende")], current_agent="tecnico"), config)
    outputs = [item for item in result["messages"] if isinstance(item, ToolMessage)]
    assert [(item.name, item.tool_call_id) for item in outputs] == [(item["name"], item["id"]) for item in calls]
    assert all(item.content == diagnosticar_problema.invoke({"sintoma": "no enciende"}) for item in outputs)
    assert all(item.status != "error" for item in outputs)
    assert event == original
    assert result["handoff_history"] == []
    assert controls["inventory_calls"] == []


@pytest.mark.parametrize("name", ["get_sourcing_capabilities", "consultar_fuentes_abastecimiento"])
def test_sourcing_historical_checkpoint_continues_without_repeating(network, name):
    module, _ = network
    saver = MemorySaver()
    config = {"configurable": {"thread_id": "sourcing-compat"}}
    event = AIMessage(content="", tool_calls=[dict(name=name, args={}, id="source")], id="source-event")
    original = deepcopy(event)
    graph = module.build_graph(checkpointer=saver)
    graph.update_state(config, {**value(), "current_agent": "compras", "messages": [event]}, as_node="compras")
    result = module.build_graph(checkpointer=saver).invoke(None, config)
    outputs = [item for item in result["messages"] if isinstance(item, ToolMessage)]
    sourcing = [item for item in outputs if item.name in {"get_sourcing_capabilities", "consultar_fuentes_abastecimiento"}]
    assert len(sourcing) == 1
    assert sourcing[0].name == name and sourcing[0].tool_call_id == "source"
    assert json.loads(sourcing[0].content) == get_sourcing_capabilities.invoke({})
    assert result["handoff_history"][0] == {"origin": "compras", "destination": "ventas"}
    assert result["supplier_offers"][0]["status"] == "PRICE_UNAVAILABLE"
    assert event == original


def test_sourcing_node_new_call_and_legacy_error_preserved():
    from app.agents.decentralized.compras import compras_node
    state = value()
    before = deepcopy(state)
    result = compras_node(state)
    assert result["messages"][0].tool_calls[0]["name"] == "get_sourcing_capabilities"
    assert result["messages"][0].tool_calls[0]["args"] == {}
    assert state == before
    state["messages"].append(ToolMessage(content="Error", name="consultar_fuentes_abastecimiento", tool_call_id="x", status="error"))
    assert not compras_node(state)["messages"][0].tool_calls


@pytest.mark.parametrize("role", ["almacen", "ventas"])
def test_diagnostic_context_readers_accept_both_names(network, role):
    module, _ = network
    import sys
    agent = sys.modules[f"app.agents.decentralized.{role}"]
    context = getattr(agent, "build_warehouse_context" if role == "almacen" else "build_sales_context")
    old = ToolMessage(content="Hipótesis preliminar", name="diagnosticar_problema", tool_call_id="old")
    new = ToolMessage(content=old.content, name="diagnose_issue", tool_call_id="new")
    assert context({"messages": [old]}) == context({"messages": [new]})
