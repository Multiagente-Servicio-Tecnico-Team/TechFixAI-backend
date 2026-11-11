import importlib
import json
from copy import deepcopy

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver

from test_software_e2e import network
from test_compras import value


def registered(graph):
    return graph.get_graph().nodes["compras_tools"].data.tools_by_name


def test_initial_imports_order_and_identity(network):
    module, _ = network
    agent = importlib.import_module("app.agents.decentralized.compras")
    assert module.purchasing_tools is module.compras_tools is agent.purchasing_tools is agent.compras_tools
    assert [tool.name for tool in agent.purchasing_tools] == ["get_sourcing_capabilities", "transfer_to_sales"]
    assert module._resolve_purchasing_tools() is agent.purchasing_tools
    tools = registered(module.build_graph())
    assert set(tools) == {"get_sourcing_capabilities", "transfer_to_sales", "consultar_fuentes_abastecimiento", "transferir_a_ventas"}
    assert all(tools[tool.name] is tool for tool in agent.purchasing_tools)


@pytest.mark.parametrize("style", ["english", "legacy", "both"])
def test_reassignment_and_monkeypatch_restoration(network, monkeypatch, style):
    module, _ = network
    initial = module.purchasing_tools
    replacement = [initial[0].model_copy()]
    with monkeypatch.context() as patch:
        if style in {"english", "both"}:
            patch.setattr(module, "purchasing_tools", replacement)
        if style in {"legacy", "both"}:
            patch.setattr(module, "compras_tools", replacement)
        assert module._resolve_purchasing_tools() is replacement
        tools = registered(module.build_graph())
        assert tools[replacement[0].name] is replacement[0]
        assert set(tools) == {"get_sourcing_capabilities", "consultar_fuentes_abastecimiento", "transferir_a_ventas"}
    assert module._resolve_purchasing_tools() is initial


def test_equal_but_distinct_replacements_conflict_without_equality(network, monkeypatch):
    module, _ = network
    class IdentityOnlyList(list):
        def __eq__(self, other):
            raise AssertionError("Equality must not resolve registries")
    monkeypatch.setattr(module, "purchasing_tools", IdentityOnlyList(module.purchasing_tools))
    monkeypatch.setattr(module, "compras_tools", IdentityOnlyList(module.compras_tools))
    with pytest.raises(ValueError, match="Conflicting purchasing tool registries"):
        module.build_graph()


def test_shared_mutation_is_visible_without_rebuilding_registry(network):
    module, _ = network
    initial = module.purchasing_tools
    previous = list(initial)
    replacement = initial[0].model_copy()
    try:
        initial[:] = [replacement]
        assert module.compras_tools is initial is module._resolve_purchasing_tools()
        assert registered(module.build_graph())[replacement.name] is replacement
    finally:
        initial[:] = previous


def test_consecutive_graphs_keep_captured_tools_and_topology(network, monkeypatch):
    module, _ = network
    original = module.build_graph()
    first, second = (module.purchasing_tools[0].model_copy() for _ in range(2))
    monkeypatch.setattr(module, "purchasing_tools", [first])
    graph_a = module.build_graph()
    monkeypatch.setattr(module, "purchasing_tools", [second])
    graph_b = module.build_graph()
    assert registered(graph_a)[first.name] is first
    assert registered(graph_b)[second.name] is second
    assert registered(original)[first.name] is module.compras_tools[0]
    assert set(graph_a.nodes) == set(graph_b.nodes) == set(original.nodes)
    edges = lambda graph: {(edge.source, edge.target) for edge in graph.get_graph().edges}
    assert edges(original) == edges(graph_a) == edges(graph_b)
    assert graph_a.interrupt_before_nodes == original.interrupt_before_nodes


@pytest.mark.parametrize("name", ["purchasing_tools", "compras_tools"])
def test_agent_rebinding_does_not_sync_graph_imports(network, monkeypatch, name):
    module, _ = network
    agent = importlib.import_module("app.agents.decentralized.compras")
    captured = module.purchasing_tools
    monkeypatch.setattr(agent, name, [])
    assert module._resolve_purchasing_tools() is captured
    assert registered(module.build_graph())[captured[0].name] is captured[0]


@pytest.mark.parametrize("style", ["english", "legacy", "mixed"])
@pytest.mark.parametrize("registry", ["purchasing_tools", "compras_tools"])
def test_toolnode_and_checkpoint_resume_keep_calls_and_cycle_token(network, monkeypatch, style, registry):
    module, _ = network
    from app.agents.decentralized.handoffs import progress_token
    from app.agents.decentralized.tools.compras_tools import consultar_fuentes_abastecimiento
    new = module.purchasing_tools[0].model_copy()
    monkeypatch.setattr(module, registry, [new])
    calls = [dict(name=name, args={}, id=str(index)) for index, name in enumerate(
        [new.name] if style == "english" else [consultar_fuentes_abastecimiento.name] if style == "legacy"
        else [new.name, consultar_fuentes_abastecimiento.name])]
    event = AIMessage(content="", id="event", tool_calls=calls)
    state = value()
    state.update(messages=[HumanMessage(content="Consultar SSD de prueba", id="human"), event], current_agent="compras",
                 handoff_history=[{"origin": "almacen", "destination": "compras"}], handoff_count=1)
    before = deepcopy(state)
    token = progress_token(state)
    saver = MemorySaver()
    config = {"configurable": {"thread_id": "purchasing-registry"}}
    graph = module.build_graph(checkpointer=saver)
    graph.update_state(config, state, as_node="compras")
    def forbidden(state):
        raise AssertionError("Turn preparation must not run on resume")
    monkeypatch.setattr(module, "prepare_turn", forbidden)
    result = module.build_graph(checkpointer=saver).invoke(None, config, interrupt_after=["auditar_compras"])
    outputs = [message for message in result["messages"] if isinstance(message, ToolMessage)]
    assert [(message.name, message.tool_call_id) for message in outputs] == [(call["name"], call["id"]) for call in calls]
    assert all(message.status != "error" for message in outputs)
    assert [json.loads(message.content) for message in outputs] == [
        (new if call["name"] == new.name else consultar_fuentes_abastecimiento).invoke({}) for call in calls]
    assert state == before and progress_token(state) == token
    assert result["handoff_history"] == state["handoff_history"] and result["handoff_count"] == 1
    assert not result.get("payment_id") and not result.get("quote_id")
