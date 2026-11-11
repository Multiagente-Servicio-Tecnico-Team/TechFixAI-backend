import importlib
import importlib.util
import json
from pathlib import Path
import sys
from unittest.mock import MagicMock
from copy import deepcopy

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver

from test_software_e2e import network


GROUPS = [("ventas", "sales"), ("almacen", "warehouse")]
ACTIVE = {
    "ventas": ["transfer_to_billing", "request_inventory", "transfer_to_support", "identify_quote_service",
               "transfer_to_hardware", "consultar_base_conocimiento"],
    "almacen": ["check_inventory", "transfer_to_sales", "transfer_to_purchasing"],
}
LEGACY = {
    "ventas": ["transferir_a_facturacion", "transferir_a_soporte", "transferir_a_tecnico", "generar_cotizacion", "solicitar_inventario"],
    "almacen": ["transferir_a_ventas", "transferir_a_compras", "consultar_inventario"],
}


def registered(graph, role):
    return graph.get_graph().nodes[role + "_tools"].data.tools_by_name


@pytest.mark.parametrize("role,canonical", GROUPS)
def test_imports_initial_identity_and_exact_registry(network, role, canonical):
    module, _ = network
    agent = importlib.import_module("app.agents.decentralized." + role)
    active = getattr(agent, canonical + "_tools")
    assert active is getattr(agent, role + "_tools") is getattr(module, canonical + "_tools") is getattr(module, role + "_tools")
    assert [tool.name for tool in active] == ACTIVE[role]
    tools = registered(module.build_graph(), role)
    assert list(tools) == ACTIVE[role] + LEGACY[role]
    assert all(tools[tool.name] is tool for tool in active)


@pytest.mark.parametrize("role,canonical", GROUPS)
@pytest.mark.parametrize("style", ["english", "legacy", "both"])
def test_reassignment_resolution_and_restoration(network, monkeypatch, role, canonical, style):
    module, _ = network
    initial = getattr(module, canonical + "_tools")
    resolve = getattr(module, "_resolve_" + canonical + "_tools")
    replacement = [initial[0].model_copy()]
    with monkeypatch.context() as patch:
        for name in ([canonical] if style == "english" else [role] if style == "legacy" else [canonical, role]):
            patch.setattr(module, name + "_tools", replacement)
        assert resolve() is replacement
        tools = registered(module.build_graph(), role)
        assert list(tools) == [replacement[0].name] + LEGACY[role]
        assert tools[replacement[0].name] is replacement[0]
    assert resolve() is initial


@pytest.mark.parametrize("role,canonical", GROUPS)
def test_conflicts_use_identity_not_equality(network, monkeypatch, role, canonical):
    module, _ = network
    class IdentityOnlyList(list):
        def __eq__(self, other):
            raise AssertionError("Equality must not resolve registries")
    original = getattr(module, canonical + "_tools")
    monkeypatch.setattr(module, canonical + "_tools", IdentityOnlyList(original))
    monkeypatch.setattr(module, role + "_tools", IdentityOnlyList(original))
    with pytest.raises(ValueError, match="Conflicting " + canonical + " tool registries"):
        module.build_graph()


@pytest.mark.parametrize("role,canonical", GROUPS)
def test_shared_mutation_preserves_identity(network, role, canonical):
    module, _ = network
    initial = getattr(module, canonical + "_tools")
    previous = list(initial)
    replacement = initial[0].model_copy()
    try:
        initial[:] = [replacement]
        assert getattr(module, role + "_tools") is initial
        assert getattr(module, "_resolve_" + canonical + "_tools")() is initial
        assert registered(module.build_graph(), role)[replacement.name] is replacement
    finally:
        initial[:] = previous


@pytest.mark.parametrize("role,canonical", GROUPS)
def test_consecutive_graphs_preserve_captured_tools_routes_and_interrupts(network, monkeypatch, role, canonical):
    module, _ = network
    original = module.build_graph()
    initial = getattr(module, canonical + "_tools")
    first, second = (initial[0].model_copy() for _ in range(2))
    monkeypatch.setattr(module, canonical + "_tools", [first])
    graph_a = module.build_graph()
    monkeypatch.setattr(module, canonical + "_tools", [second])
    graph_b = module.build_graph()
    assert registered(graph_a, role)[first.name] is first
    assert registered(graph_b, role)[second.name] is second
    assert registered(original, role)[first.name] is initial[0]
    assert set(original.nodes) == set(graph_a.nodes) == set(graph_b.nodes)
    edges = lambda graph: {(edge.source, edge.target) for edge in graph.get_graph().edges}
    assert edges(original) == edges(graph_a) == edges(graph_b)
    assert original.interrupt_before_nodes == graph_a.interrupt_before_nodes == graph_b.interrupt_before_nodes


@pytest.mark.parametrize("role,canonical", GROUPS)
@pytest.mark.parametrize("style", ["english", "legacy"])
def test_agent_rebinding_does_not_sync_captured_graph_references(network, monkeypatch, role, canonical, style):
    module, _ = network
    agent = importlib.import_module("app.agents.decentralized." + role)
    initial = getattr(module, canonical + "_tools")
    monkeypatch.setattr(agent, (canonical if style == "english" else role) + "_tools", [])
    assert getattr(module, "_resolve_" + canonical + "_tools")() is initial
    assert registered(module.build_graph(), role)[initial[0].name] is initial[0]


@pytest.mark.parametrize("sales_style", ["sales_tools", "ventas_tools"])
@pytest.mark.parametrize("warehouse_style", ["warehouse_tools", "almacen_tools"])
def test_registries_do_not_interfere_with_each_other_or_purchasing(network, monkeypatch, sales_style, warehouse_style):
    module, _ = network
    sales = module.sales_tools[0].model_copy()
    warehouse = module.warehouse_tools[0].model_copy()
    purchasing = module._resolve_purchasing_tools()
    monkeypatch.setattr(module, sales_style, [sales])
    monkeypatch.setattr(module, warehouse_style, [warehouse])
    graph = module.build_graph()
    assert registered(graph, "ventas")[sales.name] is sales
    assert registered(graph, "almacen")[warehouse.name] is warehouse
    assert module._resolve_purchasing_tools() is purchasing
    assert all(registered(graph, "compras")[tool.name] is tool for tool in purchasing)


@pytest.mark.parametrize("role,canonical", GROUPS)
def test_exact_model_initialization_binding_and_no_rebinding(network, monkeypatch, role, canonical):
    graph_module, _ = network
    groq = sys.modules["langchain_groq"]
    original = groq.ChatGroq
    created, bindings = [], []
    class CountingGroq(original):
        def __init__(self, **kwargs):
            created.append(self)
            super().__init__(**kwargs)
        def bind_tools(self, tools, **kwargs):
            bound = super().bind_tools(tools, **kwargs)
            bindings.append((tools, kwargs, bound))
            return bound
    monkeypatch.setattr(groq, "ChatGroq", CountingGroq)
    path = Path(__file__).resolve().parents[1] / f"app/agents/decentralized/{role}.py"
    if role == "almacen":
        path = path.with_name("warehouse.py")
    elif role == "ventas":
        path = path.with_name("sales.py")
    spec = importlib.util.spec_from_file_location("isolated_registry_" + role, path)
    agent = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(agent)
    active = getattr(agent, canonical + "_tools")
    assert len(created) == len(bindings) == 1
    assert bindings[0][0] is active is getattr(agent, role + "_tools")
    assert [tool.name for tool in active] == ACTIVE[role]
    assert bindings[0][1] == {}
    bound = bindings[0][2]
    assert getattr(agent, role + "_llm") is bound
    for name in (role, canonical):
        monkeypatch.setattr(agent, name + "_tools", [])
    monkeypatch.setattr(graph_module, canonical + "_tools", [])
    graph_module.build_graph()
    assert len(created) == len(bindings) == 1
    assert getattr(agent, role + "_llm") is bound


@pytest.mark.parametrize("role,canonical", GROUPS)
def test_registry_override_preserves_legacy_model_monkeypatch(network, monkeypatch, role, canonical):
    graph_module, _ = network
    agent = importlib.import_module("app.agents.decentralized." + role)
    original = getattr(agent, role + "_llm")
    monkeypatch.setattr(graph_module, canonical + "_tools", [])
    graph_module.build_graph()
    assert getattr(agent, role + "_llm") is original
    model = MagicMock()
    response = (AIMessage(content="", tool_calls=[dict(name="request_inventory", args={"query": "SSD de prueba"}, id="model")])
                if role == "ventas" else AIMessage(content="Orientacion controlada"))
    model.invoke.return_value = response
    monkeypatch.setattr(agent, role + "_llm", model)
    result = getattr(agent, canonical + "_node")({"messages": [HumanMessage(content="Consulta general")]})
    model.invoke.assert_called_once()
    assert result["messages"][0] is response


@pytest.mark.parametrize("role,canonical", GROUPS)
@pytest.mark.parametrize("style", ["english", "legacy", "mixed"])
@pytest.mark.parametrize("registry_style", ["english", "legacy"])
def test_checkpoint_calls_preserve_quote_and_inventory_results(network, monkeypatch, role, canonical, style, registry_style):
    module, controls = network
    active_name = "identify_quote_service" if role == "ventas" else "check_inventory"
    replacement = next(tool for tool in getattr(module, canonical + "_tools") if tool.name == active_name).model_copy()
    monkeypatch.setattr(module, (canonical if registry_style == "english" else role) + "_tools", [replacement])
    variants = ([dict(name="identify_quote_service", args={"service": "diagnostico"}, id="new"),
                 dict(name="generar_cotizacion", args={"servicio": "diagnostico"}, id="old")]
                if role == "ventas" else
                [dict(name="check_inventory", args={"part_name": "SSD de prueba", "quantity": 1}, id="new"),
                 dict(name="consultar_inventario", args={"nombre_repuesto": "SSD de prueba", "cantidad": 1}, id="old")])
    calls = variants if style == "mixed" else [variants[style == "legacy"]]
    event = AIMessage(content="", id="event", tool_calls=calls)
    before = deepcopy(event)
    state = dict(messages=[HumanMessage(content="Consulta", id="human"), event], current_agent=role,
                 handoff_count=0, handoff_history=[], handoff_records=[], request_revision=2)
    if role == "almacen":
        state.update(required_parts=[dict(name="SSD de prueba", quantity=1)], inventory_revision=2,
                     inventory_pending=True, inventory_requested_by="ventas")
    saver = MemorySaver()
    config = {"configurable": {"thread_id": "sales-warehouse-registry"}}
    graph = module.build_graph(checkpointer=saver)
    graph.update_state(config, state, as_node=role)
    def forbidden(state):
        raise AssertionError("Turn preparation must not run during resume")
    monkeypatch.setattr(module, "prepare_turn", forbidden)
    result = module.build_graph(checkpointer=saver).invoke(None, config, interrupt_after=["auditar_" + role])
    outputs = [message for message in result["messages"] if isinstance(message, ToolMessage)]
    assert [(message.name, message.tool_call_id) for message in outputs] == [(call["name"], call["id"]) for call in calls]
    assert all(message.status != "error" for message in outputs)
    assert event == before
    if role == "ventas":
        assert result["handoff_history"] == [] and result["handoff_count"] == 0
        expected = replacement.invoke(variants[0]["args"])
        assert [message.content for message in outputs] == [expected] * len(calls)
        assert controls["inventory_calls"] == []
    else:
        assert result["handoff_history"] == [{"origin": "almacen", "destination": "ventas"}]
        assert result["handoff_count"] == 1 and len(result["handoff_records"]) == 1
        assert len(controls["inventory_calls"]) == len(calls)
        assert all(call == ("SSD de prueba", 1) for call in controls["inventory_calls"])
        assert all(json.loads(message.content)["available"] is True for message in outputs)
        assert result["inventory_pending"] is False and result["inventory_revision"] == 2
        assert len(result["inventory_results"]) == 1
    assert not result.get("quote_id") and not result.get("payment_id")
