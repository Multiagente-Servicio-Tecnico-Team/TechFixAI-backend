import importlib
from copy import deepcopy

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver

from test_software_e2e import network


def registered(graph):
    return graph.get_graph().nodes["garantia_tools"].data.tools_by_name


def test_original_registry_is_shared_by_all_exports(network):
    module, _ = network
    agent = importlib.import_module("app.agents.decentralized.garantia")
    source = importlib.import_module("app.agents.decentralized.tools.warranty_handoff_tools")
    assert source.warranty_handoff_tools is agent.warranty_tools is agent.garantia_tools
    assert module.warranty_tools is module.garantia_tools is agent.warranty_tools
    assert [tool.name for tool in agent.warranty_tools] == ["transfer_to_logistics", "transfer_to_support"]
    tools = registered(module.build_graph())
    assert list(tools) == ["transfer_to_logistics", "transfer_to_support", "transferir_a_logistica", "transferir_a_soporte"]
    assert all(tools[tool.name] is tool for tool in source.warranty_handoff_tools)


@pytest.mark.parametrize("names", [("warranty_tools",), ("garantia_tools",), ("warranty_tools", "garantia_tools")])
def test_reassignment_and_monkeypatch_restoration(network, monkeypatch, names):
    module, _ = network
    initial = module.warranty_tools
    replacement = [initial[0].model_copy()]
    with monkeypatch.context() as patch:
        for name in names:
            patch.setattr(module, name, replacement)
        assert module._resolve_warranty_tools() is replacement
        tools = registered(module.build_graph())
        assert list(tools) == ["transfer_to_logistics", "transferir_a_logistica", "transferir_a_soporte"]
        assert tools[replacement[0].name] is replacement[0]
    assert module._resolve_warranty_tools() is initial


def test_conflicting_replacements_never_compare_equality(network, monkeypatch):
    module, _ = network
    class IdentityOnlyList(list):
        def __eq__(self, other):
            raise AssertionError("Equality must not resolve registries")
    monkeypatch.setattr(module, "warranty_tools", IdentityOnlyList(module.warranty_tools))
    monkeypatch.setattr(module, "garantia_tools", IdentityOnlyList(module.garantia_tools))
    with pytest.raises(ValueError, match="Conflicting warranty tool registries"):
        module.build_graph()


def test_shared_source_mutation_is_visible_and_restored(network):
    module, _ = network
    source = importlib.import_module("app.agents.decentralized.tools.warranty_handoff_tools")
    agent = importlib.import_module("app.agents.decentralized.garantia")
    initial = source.warranty_handoff_tools
    previous = list(initial)
    replacement = initial[0].model_copy()
    try:
        initial[:] = [replacement]
        assert initial is agent.warranty_tools is agent.garantia_tools is module._resolve_warranty_tools()
        assert registered(module.build_graph())[replacement.name] is replacement
    finally:
        initial[:] = previous


def test_consecutive_graphs_keep_tools_topology_and_interrupts(network, monkeypatch):
    module, _ = network
    original = module.build_graph()
    initial = module.warranty_tools
    first, second = (initial[0].model_copy() for _ in range(2))
    monkeypatch.setattr(module, "warranty_tools", [first])
    graph_a = module.build_graph()
    monkeypatch.setattr(module, "warranty_tools", [second])
    graph_b = module.build_graph()
    assert registered(original)[first.name] is initial[0]
    assert registered(graph_a)[first.name] is first
    assert registered(graph_b)[second.name] is second
    assert set(original.nodes) == set(graph_a.nodes) == set(graph_b.nodes)
    edges = lambda graph: {(edge.source, edge.target) for edge in graph.get_graph().edges}
    assert edges(original) == edges(graph_a) == edges(graph_b)
    assert original.interrupt_before_nodes == graph_a.interrupt_before_nodes == graph_b.interrupt_before_nodes


@pytest.mark.parametrize("name", ["warranty_tools", "garantia_tools"])
def test_agent_rebinding_does_not_sync_graph_imports(network, monkeypatch, name):
    module, _ = network
    agent = importlib.import_module("app.agents.decentralized.garantia")
    initial = module.warranty_tools
    monkeypatch.setattr(agent, name, [])
    assert module._resolve_warranty_tools() is initial
    assert registered(module.build_graph())[initial[0].name] is initial[0]


@pytest.mark.parametrize("registry", ["warranty_tools", "garantia_tools"])
@pytest.mark.parametrize("style", ["english", "legacy", "mixed"])
def test_toolnode_and_checkpoint_preserve_calls_and_first_handoff(network, monkeypatch, registry, style):
    module, _ = network
    replacement = [tool.model_copy() for tool in module.warranty_tools]
    monkeypatch.setattr(module, registry, replacement)
    calls = [dict(name="transfer_to_support", args={"reason": "Evaluar"}, id="new")] if style == "english" else [
        dict(name="transferir_a_soporte", args={"motivo": "Evaluar"}, id="old")]
    if style == "mixed":
        calls.append(dict(name="transfer_to_logistics", args={"reason": "Evaluar"}, id="second"))
    event = AIMessage(content="", id="event", tool_calls=calls)
    before = deepcopy(event)
    state = dict(messages=[HumanMessage(content="Consulta", id="human"), event], current_agent="garantia",
                 handoff_history=[], handoff_records=[], handoff_count=0, request_revision=2)
    saver = MemorySaver()
    config = {"configurable": {"thread_id": "warranty-registry"}}
    graph = module.build_graph(checkpointer=saver)
    graph.update_state(config, state, as_node="garantia")
    def forbidden(state):
        raise AssertionError("Turn preparation must not run during resume")
    monkeypatch.setattr(module, "prepare_turn", forbidden)
    result = module.build_graph(checkpointer=saver).invoke(None, config, interrupt_after=["auditar_garantia"])
    outputs = [message for message in result["messages"] if isinstance(message, ToolMessage)]
    assert [(message.name, message.tool_call_id) for message in outputs] == [(call["name"], call["id"]) for call in calls]
    assert all(message.status != "error" for message in outputs)
    tools = registered(graph)
    assert [message.content for message in outputs] == [tools[call["name"]].invoke(call["args"]) for call in calls]
    assert event == before
    assert result["handoff_history"] == [{"origin": "garantia", "destination": "soporte"}]
    assert result["handoff_count"] == 1 and len(result["handoff_records"]) == 1
    assert not result.get("warranty_claim_id") and not result.get("logistics_record_id")


def test_warranty_override_leaves_other_migrated_registries_untouched(network, monkeypatch):
    module, _ = network
    originals = {name: getattr(module, "_resolve_" + name + "_tools")() for name in ("purchasing", "billing", "logistics")}
    monkeypatch.setattr(module, "warranty_tools", [module.warranty_tools[0].model_copy()])
    graph = module.build_graph()
    for name, role in [("purchasing", "compras"), ("billing", "facturacion"), ("logistics", "logistica")]:
        assert getattr(module, "_resolve_" + name + "_tools")() is originals[name]
        tools = graph.get_graph().nodes[role + "_tools"].data.tools_by_name
        assert all(tools[tool.name] is tool for tool in originals[name])
