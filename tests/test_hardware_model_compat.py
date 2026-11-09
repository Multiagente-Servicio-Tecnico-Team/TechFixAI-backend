import importlib
import importlib.util
from copy import deepcopy
from pathlib import Path
import sys
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver

from test_software_e2e import network


PAIRS = [("hardware_llm", "tecnico_llm", "_INITIAL_HARDWARE_LLM", "Consulta general"),
         ("hardware_llm_rag", "tecnico_llm_rag", "_INITIAL_HARDWARE_LLM_RAG", "Consulta documentacion tecnica")]


def agent():
    return importlib.import_module("app.agents.decentralized.tecnico")


@pytest.mark.parametrize("canonical,legacy,initial,text", PAIRS)
def test_initial_imports_keep_each_original_model(network, canonical, legacy, initial, text):
    module = agent()
    exports = {}
    exec(f"from app.agents.decentralized.tecnico import {canonical}, {legacy}", exports)
    assert exports[canonical] is exports[legacy] is getattr(module, initial)
    assert getattr(module, "_resolve_" + canonical)() is exports[canonical]
    assert module.hardware_llm is not module.hardware_llm_rag


def test_single_base_and_exact_two_bindings_keep_tools_order_and_models(network, monkeypatch):
    groq = sys.modules["langchain_groq"]
    original = groq.ChatGroq
    created, bindings = [], []
    class CountingGroq(original):
        def __init__(self, **kwargs):
            created.append(self)
            super().__init__(**kwargs)
        def bind_tools(self, tools, **kwargs):
            bound = super().bind_tools(tools, **kwargs)
            bindings.append((self, tools, kwargs, bound))
            return bound
    monkeypatch.setattr(groq, "ChatGroq", CountingGroq)
    path = Path(__file__).resolve().parents[1] / "app/agents/decentralized/hardware.py"
    spec = importlib.util.spec_from_file_location("isolated_hardware_models", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert len(created) == 1 and len(bindings) == 2
    assert bindings[0][0] is bindings[1][0] is module.llm is created[0]
    assert bindings[0][1] is module.hardware_tools is module.tecnico_tools
    assert bindings[0][2] == {}
    assert bindings[1][1] == [module.consultar_base_conocimiento]
    assert bindings[1][1][0] is module.consultar_base_conocimiento
    assert bindings[1][2] == {"tool_choice": "required"}
    assert bindings[0][3] is module.hardware_llm is module.tecnico_llm
    assert bindings[1][3] is module.hardware_llm_rag is module.tecnico_llm_rag
    for text in ("Consulta general", "Consulta documentacion tecnica"):
        module.hardware_node({"messages": [HumanMessage(content=text)]})
    assert len(created) == 1 and len(bindings) == 2


@pytest.mark.parametrize("canonical,legacy,initial,text", PAIRS)
@pytest.mark.parametrize("style", ["english", "legacy", "both"])
@pytest.mark.parametrize("with_tools", [False, True])
def test_reassignment_selection_arguments_identity_and_restoration(network, monkeypatch, canonical, legacy, initial, text, style, with_tools):
    module = agent()
    original = getattr(module, initial)
    other = "hardware_llm_rag" if canonical == "hardware_llm" else "hardware_llm"
    other_original = getattr(module, "_resolve_" + other)()
    response = (AIMessage(content="", tool_calls=[dict(name="consultar_base_conocimiento", args={"consulta": "Documento"}, id="tool")])
                if with_tools else AIMessage(content="Orientacion controlada"))
    model = MagicMock()
    model.invoke.return_value = response
    history = [HumanMessage(content=text, id="human")]
    before = deepcopy(history)
    with monkeypatch.context() as patch:
        for name in ([canonical] if style == "english" else [legacy] if style == "legacy" else [canonical, legacy]):
            patch.setattr(module, name, model)
        assert getattr(module, "_resolve_" + canonical)() is model
        assert getattr(module, "_resolve_" + other)() is other_original
        result = module.hardware_node({"messages": history})
        assert result == {"current_agent": "tecnico", "messages": [response]}
        assert result["messages"][0] is response and history == before
        model.invoke.assert_called_once()
        assert model.invoke.call_args.args == ([SystemMessage(content=module.SYSTEM_PROMPT), *history],)
        assert model.invoke.call_args.kwargs == {}
    assert getattr(module, "_resolve_" + canonical)() is original


@pytest.mark.parametrize("canonical,legacy,initial,text", PAIRS)
def test_conflicting_pair_fails_closed_without_affecting_other_model(network, monkeypatch, canonical, legacy, initial, text):
    module = agent()
    class IdentityOnlyModel:
        def __eq__(self, other):
            raise AssertionError("Equality must not resolve models")
        def invoke(self, messages):
            raise AssertionError("Conflicting models must not run")
    other = "hardware_llm_rag" if canonical == "hardware_llm" else "hardware_llm"
    other_original = getattr(module, "_resolve_" + other)()
    monkeypatch.setattr(module, canonical, IdentityOnlyModel())
    monkeypatch.setattr(module, legacy, IdentityOnlyModel())
    with pytest.raises(ValueError, match="Conflicting hardware"):
        getattr(module, "_resolve_" + canonical)()
    assert getattr(module, "_resolve_" + other)() is other_original
    result = module.hardware_node({"messages": [HumanMessage(content=text)]})
    assert result["errors"] == ["Error en el agente Técnico: ValueError"]
    assert not result["messages"][0].tool_calls


@pytest.mark.parametrize("normal_name", ["hardware_llm", "tecnico_llm"])
@pytest.mark.parametrize("rag_name", ["hardware_llm_rag", "tecnico_llm_rag"])
def test_independent_simultaneous_replacements_and_restoration(network, monkeypatch, normal_name, rag_name):
    module = agent()
    normal_original, rag_original = module.hardware_llm, module.hardware_llm_rag
    with monkeypatch.context() as patch:
        normal, rag = MagicMock(), MagicMock()
        normal.invoke.return_value, rag.invoke.return_value = AIMessage(content="Normal"), AIMessage(content="Documental")
        patch.setattr(module, normal_name, normal)
        patch.setattr(module, rag_name, rag)
        for text, selected in [("Consulta general", normal), ("Consulta documentacion tecnica", rag)]:
            result = module.hardware_node({"messages": [HumanMessage(content=text)]})
            assert result["messages"][0] is selected.invoke.return_value
        normal.invoke.assert_called_once()
        rag.invoke.assert_called_once()
    assert module._resolve_hardware_llm() is normal_original
    assert module._resolve_hardware_llm_rag() is rag_original


@pytest.mark.parametrize("documentation,status,turn_start,expected", [
    (False, None, 0, "normal"), (True, None, 0, "rag"),
    (True, "success", 0, "normal"), (True, "error", 0, "rag"),
    (True, "success", 2, "rag"), (False, "error", 0, "normal"),
])
def test_existing_documentation_and_turn_selection_is_unchanged(network, monkeypatch, documentation, status, turn_start, expected):
    module = agent()
    normal, rag = MagicMock(), MagicMock()
    normal.invoke.return_value, rag.invoke.return_value = AIMessage(content="Normal"), AIMessage(content="Documental")
    monkeypatch.setattr(module, "hardware_llm", normal)
    monkeypatch.setattr(module, "hardware_llm_rag", rag)
    messages = [HumanMessage(content="Consulta documentacion tecnica" if documentation else "Consulta general")]
    if status:
        messages.append(ToolMessage(content="Documento fixture" if status == "success" else "Error fixture",
                                    name="consultar_base_conocimiento", tool_call_id="doc", status=status))
    before = deepcopy(messages)
    result = module.hardware_node({"messages": messages, "turn_start_index": turn_start})
    selected, unused = (normal, rag) if expected == "normal" else (rag, normal)
    selected.invoke.assert_called_once()
    unused.invoke.assert_not_called()
    assert result["messages"][0] is selected.invoke.return_value and messages == before


@pytest.mark.parametrize("canonical,legacy,initial,text", PAIRS)
@pytest.mark.parametrize("style", ["english", "legacy"])
def test_errors_preserve_controlled_response_without_new_fallback(network, monkeypatch, canonical, legacy, initial, text, style):
    module = agent()
    selected, unused = MagicMock(), MagicMock()
    selected.invoke.side_effect = RuntimeError("private detail")
    monkeypatch.setattr(module, canonical if style == "english" else legacy, selected)
    other = "hardware_llm_rag" if canonical == "hardware_llm" else "hardware_llm"
    monkeypatch.setattr(module, other, unused)
    result = module.hardware_node({"messages": [HumanMessage(content=text)]})
    selected.invoke.assert_called_once()
    unused.invoke.assert_not_called()
    assert result["errors"] == ["Error en el agente Técnico: RuntimeError"]
    assert "private detail" not in str(result)


@pytest.mark.parametrize("legacy_names", [False, True])
def test_rag_tool_checkpoint_resumes_with_regular_model_and_historical_handoff(network, monkeypatch, legacy_names):
    graph_module, controls = network
    module = agent()
    regular, rag = MagicMock(), MagicMock()
    rag.invoke.return_value = AIMessage(content="", id="rag-event", tool_calls=[dict(name="consultar_base_conocimiento", args={"consulta": "Documento fixture"}, id="rag-call")])
    handoff_name = "transferir_a_software" if legacy_names else "transfer_to_software"
    regular.invoke.return_value = AIMessage(content="", id="handoff-event", tool_calls=[dict(name=handoff_name, args={"motivo" if legacy_names else "reason": "Evaluar"}, id="handoff-call")])
    monkeypatch.setattr(module, "tecnico_llm" if legacy_names else "hardware_llm", regular)
    monkeypatch.setattr(module, "tecnico_llm_rag" if legacy_names else "hardware_llm_rag", rag)
    saver = MemorySaver()
    config = {"configurable": {"thread_id": "hardware-models"}}
    graph = graph_module.build_graph(checkpointer=saver)
    graph.update_state(config, {"messages": [HumanMessage(content="Consulta documentacion tecnica", id="human")],
        "current_agent": "tecnico", "handoff_count": 0, "handoff_history": [], "handoff_records": [],
        "request_revision": 2}, as_node="preparar_turno")
    def forbidden(state):
        raise AssertionError("Turn preparation must not run on resume")
    monkeypatch.setattr(graph_module, "prepare_turn", forbidden)
    result = graph_module.build_graph(checkpointer=saver).invoke(None, config, interrupt_after=["auditar_tecnico"])
    rag.invoke.assert_called_once()
    regular.invoke.assert_not_called()
    assert controls["rag_calls"] == ["Documento fixture"]
    result = graph_module.build_graph(checkpointer=saver).invoke(None, config, interrupt_after=["auditar_tecnico"])
    regular.invoke.assert_called_once()
    rag.invoke.assert_called_once()
    outputs = [message for message in result["messages"] if isinstance(message, ToolMessage)]
    assert [(message.name, message.tool_call_id) for message in outputs] == [("consultar_base_conocimiento", "rag-call"), (handoff_name, "handoff-call")]
    assert all(message.status != "error" for message in outputs)
    assert result["handoff_history"] == [{"origin": "tecnico", "destination": "software"}]
    assert result["handoff_count"] == 1 and len(result["handoff_records"]) == 1
