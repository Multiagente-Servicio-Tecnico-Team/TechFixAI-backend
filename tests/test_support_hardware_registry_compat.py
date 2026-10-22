import importlib
import importlib.util
from pathlib import Path
import sys
from unittest.mock import MagicMock
from copy import deepcopy

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver

from test_software_e2e import network


GROUPS = [("soporte", "support"), ("tecnico", "hardware")]
ACTIVE = {
    "soporte": ["transfer_to_warranty", "transfer_to_logistics", "transfer_to_billing", "get_ticket_status",
                "transfer_to_hardware", "transfer_to_sales", "transfer_to_software", "consultar_base_conocimiento"],
    "tecnico": ["transfer_to_logistics", "transfer_to_support", "transfer_to_software", "diagnose_issue",
                "transfer_to_sales", "transfer_to_warehouse", "consultar_base_conocimiento"],
}
LEGACY = {
    "soporte": ["transferir_a_garantia", "transferir_a_logistica", "transferir_a_facturacion", "transferir_a_tecnico",
                "transferir_a_ventas", "transferir_a_software", "consultar_estado_ticket"],
    "tecnico": ["transferir_a_logistica", "transferir_a_soporte", "transferir_a_software", "transferir_a_ventas",
                "transferir_a_almacen", "diagnosticar_problema"],
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
    new = next(tool for tool in getattr(module, canonical + "_tools") if tool.name == "transfer_to_software").model_copy()
    monkeypatch.setattr(module, (canonical if registry_style == "english" else role) + "_tools", [new])
    names = [new.name] if style == "english" else ["transferir_a_software"] if style == "legacy" else [new.name, "transferir_a_software"]
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
    assert result["handoff_history"] == [{"origin": role, "destination": "software"}]
    assert result["handoff_count"] == 1 and len(result["handoff_records"]) == 1
    assert not result.get("payment_id") and not result.get("logistics_record_id")


@pytest.mark.parametrize("support_style", ["support_tools", "soporte_tools"])
@pytest.mark.parametrize("hardware_style", ["hardware_tools", "tecnico_tools"])
def test_registries_do_not_interfere_with_each_other_or_purchasing(network, monkeypatch, support_style, hardware_style):
    module, _ = network
    support = module.support_tools[0].model_copy()
    hardware = module.hardware_tools[0].model_copy()
    purchasing = module._resolve_purchasing_tools()
    monkeypatch.setattr(module, support_style, [support])
    monkeypatch.setattr(module, hardware_style, [hardware])
    graph = module.build_graph()
    assert registered(graph, "soporte")[support.name] is support
    assert registered(graph, "tecnico")[hardware.name] is hardware
    assert module._resolve_purchasing_tools() is purchasing
    assert all(registered(graph, "compras")[tool.name] is tool for tool in purchasing)


@pytest.mark.parametrize("role,canonical", GROUPS)
def test_model_initialization_binds_exact_original_objects_once(network, monkeypatch, role, canonical):
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
    if role == "tecnico":
        path = path.with_name("hardware.py")
    elif role == "soporte":
        path = path.with_name("support.py")
    spec = importlib.util.spec_from_file_location("isolated_registry_" + role, path)
    agent = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(agent)
    active = getattr(agent, canonical + "_tools")
    assert len(created) == 1
    assert len(bindings) == (1 if role == "soporte" else 2)
    assert active is getattr(agent, role + "_tools") is bindings[0][0]
    assert [tool.name for tool in bindings[0][0]] == ACTIVE[role]
    assert bindings[0][1] == {}
    assert getattr(agent, role + "_llm") is bindings[0][2]
    if role == "tecnico":
        assert bindings[1][0] == [agent.consultar_base_conocimiento]
        assert bindings[1][0][0] is agent.consultar_base_conocimiento
        assert bindings[1][1] == {"tool_choice": "required"}
        assert agent.tecnico_llm_rag is bindings[1][2]
    bound_models = tuple(item[2] for item in bindings)
    for name in (role, canonical):
        monkeypatch.setattr(agent, name + "_tools", [])
    monkeypatch.setattr(graph_module, canonical + "_tools", [])
    graph_module.build_graph()
    assert len(created) == 1 and tuple(item[2] for item in bindings) == bound_models
    assert getattr(agent, role + "_llm") is bound_models[0]
    if role == "tecnico":
        assert agent.tecnico_llm_rag is bound_models[1]


@pytest.mark.parametrize("role,canonical,attribute,text", [
    ("soporte", "support", "soporte_llm", "Consulta general"),
    ("tecnico", "hardware", "tecnico_llm", "Consulta general"),
    ("tecnico", "hardware", "tecnico_llm_rag", "Consulta documentacion tecnica"),
])
def test_registry_override_keeps_legacy_model_monkeypatch_and_rag_selection(network, monkeypatch, role, canonical, attribute, text):
    graph_module, _ = network
    agent = importlib.import_module("app.agents.decentralized." + role)
    models = {name: getattr(agent, name) for name in (role + "_llm",) + (("tecnico_llm_rag",) if role == "tecnico" else ())}
    selected = MagicMock()
    response = AIMessage(content="Respuesta controlada")
    selected.invoke.return_value = response
    monkeypatch.setattr(graph_module, canonical + "_tools", [])
    graph_module.build_graph()
    assert all(getattr(agent, name) is model for name, model in models.items())
    monkeypatch.setattr(agent, attribute, selected)
    result = getattr(agent, canonical + "_node")({"messages": [HumanMessage(content=text)]})
    selected.invoke.assert_called_once()
    assert result["messages"][0] is response
