import importlib
from copy import deepcopy

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver

from test_software_e2e import network


GROUPS = [("facturacion", "billing"), ("logistica", "logistics")]
ACTIVE = {
    "facturacion": ["transfer_to_support", "transfer_to_sales", "get_financial_capabilities", "transfer_to_logistics"],
    "logistica": ["transfer_to_support"],
}
LEGACY = {
    "facturacion": ["transferir_a_soporte", "transferir_a_ventas", "transferir_a_logistica", "consultar_capacidades_financieras"],
    "logistica": ["transferir_a_soporte"],
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


@pytest.mark.parametrize("role,canonical", GROUPS)
@pytest.mark.parametrize("style", ["english", "legacy", "mixed"])
@pytest.mark.parametrize("registry_style", ["english", "legacy"])
def test_toolnode_resume_keeps_historical_calls_and_handoff(network, monkeypatch, role, canonical, style, registry_style):
    module, _ = network
    new = getattr(module, canonical + "_tools")[0].model_copy()
    monkeypatch.setattr(module, (canonical if registry_style == "english" else role) + "_tools", [new])
    names = [new.name] if style == "english" else ["transferir_a_soporte"] if style == "legacy" else [new.name, "transferir_a_soporte"]
    calls = [dict(name=name, args={"reason" if name == new.name else "motivo": "Evaluar"}, id=str(index))
             for index, name in enumerate(names)]
    event = AIMessage(content="", id="event", tool_calls=calls)
    before = deepcopy(event)
    state = dict(messages=[HumanMessage(content="Consulta", id="human"), event], current_agent=role,
                 handoff_count=0, handoff_history=[], handoff_records=[], request_revision=2)
    saver = MemorySaver()
    config = {"configurable": {"thread_id": "registry-resume"}}
    graph = module.build_graph(checkpointer=saver)
    graph.update_state(config, state, as_node=role)
    def forbidden(state):
        raise AssertionError("Turn preparation must not run during resume")
    monkeypatch.setattr(module, "prepare_turn", forbidden)
    result = module.build_graph(checkpointer=saver).invoke(None, config, interrupt_after=["auditar_" + role])
    outputs = [message for message in result["messages"] if isinstance(message, ToolMessage)]
    assert [(message.name, message.tool_call_id) for message in outputs] == [(call["name"], call["id"]) for call in calls]
    assert all(message.status != "error" for message in outputs)
    tools = registered(graph, role)
    assert [message.content for message in outputs] == [tools[call["name"]].invoke(call["args"]) for call in calls]
    assert event == before
    assert result["handoff_history"] == [{"origin": role, "destination": "soporte"}]
    assert result["handoff_count"] == 1 and len(result["handoff_records"]) == 1
    assert not result.get("payment_id") and not result.get("logistics_record_id")


@pytest.mark.parametrize("billing_style", ["billing_tools", "facturacion_tools"])
@pytest.mark.parametrize("logistics_style", ["logistics_tools", "logistica_tools"])
def test_registries_do_not_interfere_with_each_other_or_purchasing(network, monkeypatch, billing_style, logistics_style):
    module, _ = network
    billing = module.billing_tools[0].model_copy()
    logistics = module.logistics_tools[0].model_copy()
    purchasing = module._resolve_purchasing_tools()
    monkeypatch.setattr(module, billing_style, [billing])
    monkeypatch.setattr(module, logistics_style, [logistics])
    graph = module.build_graph()
    assert registered(graph, "facturacion")[billing.name] is billing
    assert registered(graph, "logistica")[logistics.name] is logistics
    assert module._resolve_purchasing_tools() is purchasing
    assert all(registered(graph, "compras")[tool.name] is tool for tool in purchasing)
