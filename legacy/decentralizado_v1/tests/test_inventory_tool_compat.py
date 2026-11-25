import ast
from copy import deepcopy
import importlib
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver
from pydantic import ValidationError

from test_software_e2e import network


ROOT = Path(__file__).resolve().parents[1]
LEGACY = {"consultar_capacidades_financieras", "diagnosticar_problema", "consultar_fuentes_abastecimiento", "consultar_inventario"}


@pytest.mark.parametrize("role", ["tecnico", "almacen", "compras", "facturacion"])
def test_active_prompt_identifiers_match_registry(network, role):
    module, _ = network
    source_role = {"facturacion": "billing", "almacen": "warehouse", "tecnico": "hardware"}.get(role, role)
    source = (ROOT / f"app/agents/decentralized/{source_role}.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    prompts = [ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.Assign)
               and any(isinstance(target, ast.Name) and target.id == "SYSTEM_PROMPT" for target in node.targets)]
    assert len(prompts) == (0 if role == "compras" else 1)
    prompt = prompts[0] if prompts else ""
    assert not any(name in prompt for name in LEGACY)
    active = {tool.name for tool in getattr(module, f"{role}_tools")}
    expected = {"tecnico": "diagnose_issue", "almacen": "check_inventory",
                "compras": "get_sourcing_capabilities", "facturacion": "get_financial_capabilities"}[role]
    assert expected in active and not active & LEGACY
    if role in {"tecnico", "almacen"}:
        assert expected in prompt


@pytest.fixture
def tools(monkeypatch):
    module = importlib.import_module("app.agents.decentralized.tools.almacen_tools")
    lookup = MagicMock(return_value=dict(requested_name="SSD", name="SSD", quantity=2,
        stock=3, available=True, found=True, unit_price="180.00"))
    monkeypatch.setattr(module, "lookup_inventory", lookup)
    return module, lookup


@pytest.mark.parametrize("name,part,quantity", [
    ("check_inventory", "part_name", "quantity"),
    ("consultar_inventario", "nombre_repuesto", "cantidad"),
])
def test_exact_schemas_defaults_and_required_fields(tools, name, part, quantity):
    module, _ = tools
    tool = getattr(module, name)
    schema = tool.args_schema.model_json_schema()
    assert tool.name == name
    assert set(schema["properties"]) == {part, quantity}
    assert schema["required"] == [part]
    assert schema["properties"][part]["type"] == "string"
    assert schema["properties"][quantity]["type"] == "integer"
    assert schema["properties"][quantity]["default"] == 1
    with pytest.raises(ValidationError):
        tool.invoke({})
    with pytest.raises(ValidationError):
        tool.invoke({"nombre_repuesto" if part == "part_name" else "part_name": "SSD"})


def test_variant_outputs_and_lookup_arguments_are_identical(tools):
    module, lookup = tools
    old = module.consultar_inventario.invoke({"nombre_repuesto": "SSD", "cantidad": 2})
    new = module.check_inventory.invoke({"part_name": "SSD", "quantity": 2})
    assert old == new
    assert lookup.call_count == 2
    assert all(call.kwargs == dict(requested_name="SSD", quantity=2) for call in lookup.call_args_list)
    assert module.check_inventory.description == module.consultar_inventario.description
    lookup.reset_mock()
    module.check_inventory.invoke({"part_name": "SSD"})
    lookup.assert_called_once_with(requested_name="SSD", quantity=1)


@pytest.mark.parametrize("name,part,quantity", [
    ("check_inventory", "part_name", "quantity"),
    ("consultar_inventario", "nombre_repuesto", "cantidad"),
])
@pytest.mark.parametrize("bad_name,bad_quantity", [(" ", 1), ("SSD", 0), ("SSD", -1)])
def test_same_invalid_arguments_never_query(tools, name, part, quantity, bad_name, bad_quantity):
    module, lookup = tools
    with pytest.raises(ValueError):
        getattr(module, name).invoke({part: bad_name, quantity: bad_quantity})
    lookup.assert_not_called()


def test_exact_graph_registry_and_no_override_of_injected_legacy(network, monkeypatch):
    module, _ = network
    active = [tool.name for tool in module.almacen_tools]
    assert active == ["check_inventory", "transfer_to_sales", "transfer_to_purchasing"]
    node = module.build_graph().get_graph().nodes["almacen_tools"].data
    assert set(node.tools_by_name) == set(active) | {"consultar_inventario", "transferir_a_ventas", "transferir_a_compras"}
    legacy = node.tools_by_name["consultar_inventario"].model_copy()
    monkeypatch.setattr(module, "almacen_tools", [legacy])
    injected = module.build_graph().get_graph().nodes["almacen_tools"].data
    assert set(injected.tools_by_name) == {legacy.name, "transferir_a_ventas", "transferir_a_compras"}
    assert injected.tools_by_name[legacy.name] is legacy


@pytest.mark.parametrize("style", ["legacy", "english", "batch"])
def test_inventory_checkpoint_executes_each_call_once(network, style):
    module, controls = network
    variants = [dict(name="consultar_inventario", args={"nombre_repuesto": "SSD de prueba", "cantidad": 1}, id="old"),
                dict(name="check_inventory", args={"part_name": "SSD de prueba", "quantity": 1}, id="new")]
    calls = variants if style == "batch" else [variants[style == "english"]]
    event = AIMessage(content="", tool_calls=calls, id="inventory-event")
    original = deepcopy(event)
    saver = MemorySaver()
    config = {"configurable": {"thread_id": "inventory-compat"}}
    state = dict(messages=[HumanMessage(content="SSD de prueba", id="user"), event], current_agent="almacen",
        required_parts=[dict(name="SSD de prueba", quantity=1)], request_revision=2,
        inventory_revision=2, inventory_pending=True, inventory_requested_by="ventas", handoff_history=[])
    graph = module.build_graph(checkpointer=saver)
    graph.update_state(config, state, as_node="almacen")
    result = module.build_graph(checkpointer=saver).invoke(None, config)
    outputs = [message for message in result["messages"] if isinstance(message, ToolMessage)
               and message.name in {"consultar_inventario", "check_inventory"}]
    assert [(message.name, message.tool_call_id) for message in outputs] == [(call["name"], call["id"]) for call in calls]
    assert all(message.status != "error" for message in outputs)
    assert len(controls["inventory_calls"]) == len(calls)
    assert all(call == ("SSD de prueba", 1) for call in controls["inventory_calls"])
    assert len(result["inventory_results"]) == 1
    assert result["inventory_pending"] is False and result["inventory_revision"] == 2
    assert result["handoff_history"] == [{"origin": "almacen", "destination": "ventas"}]
    assert event == original


@pytest.mark.parametrize("stock,destination", [(3, "ventas"), (0, "compras")])
def test_active_warehouse_call_and_real_audit(network, stock, destination):
    module, controls = network
    controls["inventory_stock"] = stock
    result = module.build_graph().invoke(dict(messages=[HumanMessage(content="SSD de prueba")], current_agent="almacen",
        required_parts=[dict(name="SSD de prueba", quantity=1)], request_revision=2,
        inventory_revision=2, inventory_pending=True))
    calls = [call for message in result["messages"] if isinstance(message, AIMessage) for call in message.tool_calls]
    assert calls[0]["name"] == "check_inventory" and calls[0]["args"] == dict(part_name="SSD de prueba", quantity=1)
    assert result["handoff_history"][0] == {"origin": "almacen", "destination": destination}
    assert controls["inventory_calls"] == [("SSD de prueba", 1)]


@pytest.mark.parametrize("name", ["check_inventory", "consultar_inventario"])
def test_failed_inventory_result_never_routes_as_verified(network, name):
    module, _ = network
    state = dict(messages=[ToolMessage(content="Unavailable", name=name, tool_call_id="failed", status="error")],
        required_parts=[dict(name="SSD", quantity=1)], inventory_pending=True, request_revision=2, inventory_revision=2)
    before = deepcopy(state)
    saved = module.guardar_inventario(state)
    assert saved["inventory_pending"] is True and saved["inventory_results"] == []
    audited = module.record_handoff({**state, **saved}, "almacen")
    assert audited["next_agent"] == "almacen" and "handoff_history" not in audited
    assert state == before


def test_obsolete_inventory_is_queried_again_but_current_result_is_reused(network):
    module, controls = network
    state = dict(messages=[HumanMessage(content="SSD de prueba")], current_agent="almacen",
        required_parts=[dict(name="SSD de prueba", quantity=1)], request_revision=2, inventory_revision=1,
        inventory_pending=False, inventory_results=[dict(requested_name="SSD de prueba", name="SSD de prueba",
            quantity=1, stock=100, unit_price="1.00", available=True, found=True)])
    result = module.build_graph().invoke(state)
    assert controls["inventory_calls"] == [("SSD de prueba", 1)]
    assert result["inventory_revision"] == 2 and result["inventory_results"][0]["unit_price"] == "180.00"
    controls["inventory_calls"].clear()
    module.build_graph().invoke({**result, "messages": [HumanMessage(content="SSD de prueba")], "current_agent": "almacen"})
    assert controls["inventory_calls"] == []
