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


def agent():
    return importlib.import_module("app.agents.decentralized.soporte")


def test_initial_imports_and_original_identity(network):
    module = agent()
    from app.agents.decentralized.soporte import support_llm, soporte_llm
    assert support_llm is soporte_llm is module._INITIAL_SUPPORT_LLM is module._resolve_support_llm()


def test_single_initialization_and_binding_with_original_registry(network, monkeypatch):
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
    path = Path(__file__).resolve().parents[1] / "app/agents/decentralized/soporte.py"
    spec = importlib.util.spec_from_file_location("isolated_support_model", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert len(created) == len(bindings) == 1
    assert module.llm is created[0]
    assert bindings[0][0] is module.support_tools is module.soporte_tools
    assert bindings[0][1] == {}
    assert bindings[0][2] is module.support_llm is module.soporte_llm
    for _ in range(2):
        module.support_node({"messages": [HumanMessage(content="Consulta general")]})
    assert len(created) == len(bindings) == 1


@pytest.mark.parametrize("names", [("support_llm",), ("soporte_llm",), ("support_llm", "soporte_llm")])
@pytest.mark.parametrize("tool_response", [False, True])
def test_reassignment_invokes_selected_model_with_unchanged_messages_and_restores(network, monkeypatch, names, tool_response):
    module = agent()
    original = module.support_llm
    response = (AIMessage(content="", tool_calls=[dict(name="transfer_to_software", args={"reason": "Evaluar"}, id="tool")])
                if tool_response else AIMessage(content="Respuesta controlada"))
    replacement = MagicMock()
    replacement.invoke.return_value = response
    history = [HumanMessage(content="Consulta general", id="human")]
    before = deepcopy(history)
    with monkeypatch.context() as patch:
        for name in names:
            patch.setattr(module, name, replacement)
        assert module._resolve_support_llm() is replacement
        result = module.support_node({"messages": history})
        assert result == {"current_agent": "soporte", "messages": [response]}
        assert result["messages"][0] is response
        replacement.invoke.assert_called_once()
        arguments, kwargs = replacement.invoke.call_args
        assert kwargs == {} and len(arguments) == 1
        assert arguments[0][0] == SystemMessage(content=module.SYSTEM_PROMPT)
        assert arguments[0][1] is history[0] and history == before
    assert module._resolve_support_llm() is original


def test_conflicts_fail_closed_without_comparing_or_invoking_models(network, monkeypatch):
    module = agent()
    class IdentityOnlyModel:
        def __eq__(self, other):
            raise AssertionError("Equality must not resolve models")
        def invoke(self, messages):
            raise AssertionError("Conflicting model must not run")
    monkeypatch.setattr(module, "support_llm", IdentityOnlyModel())
    monkeypatch.setattr(module, "soporte_llm", IdentityOnlyModel())
    with pytest.raises(ValueError, match="Conflicting support models"):
        module._resolve_support_llm()
    result = module.support_node({"messages": [HumanMessage(content="Consulta general")]})
    assert result["errors"] == ["Error en el agente Soporte: ValueError"]
    assert not result["messages"][0].tool_calls


def test_model_changes_between_invocations_and_direct_import_is_not_resynchronized(network, monkeypatch):
    module = agent()
    from app.agents.decentralized.soporte import soporte_llm as captured
    for name in ("support_llm", "soporte_llm"):
        with monkeypatch.context() as patch:
            first, second = MagicMock(), MagicMock()
            first.invoke.return_value = AIMessage(content="Primera")
            second.invoke.return_value = AIMessage(content="Segunda")
            for model in (first, second):
                patch.setattr(module, name, model)
                result = module.support_node({"messages": [HumanMessage(content="Consulta general")]})
                assert result["messages"][0] is model.invoke.return_value
            assert captured is module._INITIAL_SUPPORT_LLM
    assert module._resolve_support_llm() is captured


@pytest.mark.parametrize("name", ["support_llm", "soporte_llm"])
def test_selected_model_errors_keep_existing_safe_response(network, monkeypatch, name):
    module = agent()
    model = MagicMock()
    model.invoke.side_effect = RuntimeError("private detail")
    monkeypatch.setattr(module, name, model)
    result = module.support_node({"messages": [HumanMessage(content="Consulta general")], "errors": ["previous"]})
    model.invoke.assert_called_once()
    assert result["errors"] == ["previous", "Error en el agente Soporte: RuntimeError"]
    assert "private detail" not in str(result)


@pytest.mark.parametrize("name", ["support_llm", "soporte_llm"])
@pytest.mark.parametrize("tool_name", ["transfer_to_software", "transferir_a_software"])
def test_checkpoint_resume_invokes_current_model_and_keeps_handoff(network, monkeypatch, name, tool_name):
    graph_module, _ = network
    module = agent()
    model = MagicMock()
    event = AIMessage(content="", id="event", tool_calls=[dict(name=tool_name,
        args={"reason" if tool_name == "transfer_to_software" else "motivo": "Evaluar"}, id="call")])
    model.invoke.return_value = event
    saver = MemorySaver()
    config = {"configurable": {"thread_id": "support-model"}}
    graph = graph_module.build_graph(checkpointer=saver)
    graph.update_state(config, {"messages": [HumanMessage(content="Consulta general", id="human")],
        "current_agent": "soporte", "handoff_count": 0, "handoff_history": [], "handoff_records": [],
        "request_revision": 2}, as_node="preparar_turno")
    monkeypatch.setattr(module, name, model)
    def forbidden(state):
        raise AssertionError("Turn preparation must not run during resume")
    monkeypatch.setattr(graph_module, "prepare_turn", forbidden)
    result = graph_module.build_graph(checkpointer=saver).invoke(None, config, interrupt_after=["auditar_soporte"])
    model.invoke.assert_called_once()
    outputs = [message for message in result["messages"] if isinstance(message, ToolMessage)]
    assert [(message.name, message.tool_call_id) for message in outputs] == [(tool_name, "call")]
    assert result["handoff_history"] == [{"origin": "soporte", "destination": "software"}]
    assert result["handoff_count"] == 1 and len(result["handoff_records"]) == 1
