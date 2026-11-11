import importlib
import inspect
import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver

from test_software_e2e import network


ROOT = Path(__file__).resolve().parents[1]
ENGLISH = "app.agents.decentralized.hardware"
LEGACY = "app.agents.decentralized.tecnico"


@pytest.mark.parametrize("first", ["hardware", "tecnico"])
@pytest.mark.parametrize("style", ["importlib", "package"])
@pytest.mark.parametrize("reload_requested", [False, True])
def test_fresh_import_orders_initialize_and_bind_once(first, style, reload_requested):
    script = r'''
import importlib, json, sys
from pathlib import Path
from types import ModuleType
from langchain_core.tools import tool
sys.path.insert(0, sys.argv[1])
created, bindings, dotenv_calls = [], [], []
class FakeGroq:
    def __init__(self, **kwargs):
        created.append(kwargs)
    def bind_tools(self, tools, **kwargs):
        bound = object()
        bindings.append((self, tools, kwargs, bound))
        return bound
groq = ModuleType("langchain_groq")
groq.ChatGroq = FakeGroq
sys.modules["langchain_groq"] = groq
dotenv = ModuleType("dotenv")
dotenv.load_dotenv = lambda *args, **kwargs: dotenv_calls.append(sys._getframe(1).f_globals.get("__name__"))
sys.modules["dotenv"] = dotenv
rag = ModuleType("app.rag.tools")
@tool
def consultar_base_conocimiento(consulta: str) -> str:
    """Isolated knowledge fixture."""
    raise AssertionError("No retrieval during import")
rag.consultar_base_conocimiento = consultar_base_conocimiento
sys.modules["app.rag.tools"] = rag
def load(name):
    if sys.argv[3] == "package":
        namespace = {}
        exec("from app.agents.decentralized import " + name, namespace)
        return namespace[name]
    return importlib.import_module("app.agents.decentralized." + name)
one = load(sys.argv[2])
two = load("tecnico" if sys.argv[2] == "hardware" else "hardware")
from app.agents.decentralized import hardware, tecnico
assert one is two is hardware is tecnico
assert load("hardware") is load("tecnico") is one
assert len(created) == 1 and len(bindings) == 2
assert dotenv_calls.count("app.agents.decentralized.hardware") == 1
assert created == [dict(model="openai/gpt-oss-20b", temperature=0,
    reasoning_effort="low", model_kwargs={"parallel_tool_calls": False})]
assert bindings[0][0] is bindings[1][0] is one.llm
assert bindings[0][1] is one.hardware_tools is one.tecnico_tools
assert bindings[0][2] == {}
assert bindings[1][1] == [one.consultar_base_conocimiento]
assert bindings[1][2] == {"tool_choice": "required"}
assert bindings[0][3] is one.hardware_llm is one.tecnico_llm is one._INITIAL_HARDWARE_LLM
assert bindings[1][3] is one.hardware_llm_rag is one.tecnico_llm_rag is one._INITIAL_HARDWARE_LLM_RAG
assert one.hardware_llm is not one.hardware_llm_rag
assert one._resolve_hardware_llm() is one.hardware_llm
assert one._resolve_hardware_llm_rag() is one.hardware_llm_rag
assert one.hardware_node is one.tecnico_node
assert sys.modules["app.agents.decentralized.hardware"] is sys.modules["app.agents.decentralized.tecnico"]
assert one.__name__ == one.__spec__.name == "app.agents.decentralized.hardware"
assert Path(one.__file__).name == "hardware.py"
if sys.argv[4] == "reload":
    old_node, old_normal, old_rag, old_tools = one.hardware_node, one.hardware_llm, one.hardware_llm_rag, one.hardware_tools
    assert importlib.reload(one) is one
    assert load("hardware") is load("tecnico") is one
    assert len(created) == 2 and len(bindings) == 4
    assert created[0] == created[1]
    assert bindings[2][0] is bindings[3][0] is one.llm
    assert bindings[2][1] is one.hardware_tools is one.tecnico_tools
    assert bindings[2][2] == {}
    assert bindings[3][1] == [one.consultar_base_conocimiento]
    assert bindings[3][2] == {"tool_choice": "required"}
    assert bindings[2][3] is one.hardware_llm is one.tecnico_llm is one._INITIAL_HARDWARE_LLM
    assert bindings[3][3] is one.hardware_llm_rag is one.tecnico_llm_rag is one._INITIAL_HARDWARE_LLM_RAG
    assert one._resolve_hardware_llm() is one.hardware_llm
    assert one._resolve_hardware_llm_rag() is one.hardware_llm_rag
    assert one.hardware_node is one.tecnico_node and old_node is not one.hardware_node
    assert old_normal is not one.hardware_llm and old_rag is not one.hardware_llm_rag
    assert old_tools is not one.hardware_tools
    assert old_node.__globals__ is one.__dict__
print(json.dumps({"created": len(created), "bindings": len(bindings)}))
'''
    result = subprocess.run([sys.executable, "-B", "-c", script, str(ROOT), first, style, "reload" if reload_requested else "normal"],
                            cwd=ROOT, capture_output=True, text=True, timeout=60, check=True)
    assert json.loads(result.stdout) == {"created": 2 if reload_requested else 1, "bindings": 4 if reload_requested else 2}


def test_identity_globals_metadata_and_graph_capture(network):
    graph_module, _ = network
    english, legacy = importlib.import_module(ENGLISH), importlib.import_module(LEGACY)
    from app.agents.decentralized import hardware, tecnico
    assert english is legacy is hardware is tecnico
    assert english.hardware_node is legacy.tecnico_node is graph_module.AGENT_NODES["tecnico"]
    assert english.hardware_node.__globals__ is legacy.__dict__
    assert english.hardware_tools is legacy.tecnico_tools is graph_module.hardware_tools
    assert english.hardware_llm is legacy.tecnico_llm is english._INITIAL_HARDWARE_LLM
    assert english.hardware_llm_rag is legacy.tecnico_llm_rag is english._INITIAL_HARDWARE_LLM_RAG
    assert english.hardware_llm is not english.hardware_llm_rag
    assert english.__name__ == english.__spec__.name == ENGLISH
    assert Path(english.__file__) == ROOT / "app/agents/decentralized/hardware.py"
    assert english.hardware_node.__module__ == ENGLISH
    assert inspect.getmodule(english.hardware_node) is legacy
    assert inspect.getsourcefile(english.hardware_node) == legacy.__file__
    assert "def hardware_node(" in inspect.getsource(english.hardware_node)


@pytest.mark.parametrize("path", [ENGLISH, LEGACY])
@pytest.mark.parametrize("attribute", ["hardware_llm", "tecnico_llm", "hardware_llm_rag", "tecnico_llm_rag"])
def test_model_monkeypatch_invokes_from_other_path_and_restores(network, monkeypatch, path, attribute):
    source = importlib.import_module(path)
    peer = importlib.import_module(LEGACY if path == ENGLISH else ENGLISH)
    suffix = "_rag" if attribute.endswith("_rag") else ""
    resolve = getattr(source, "_resolve_hardware_llm" + suffix)
    other_resolve = getattr(source, "_resolve_hardware_llm" + ("" if suffix else "_rag"))
    original, untouched = resolve(), other_resolve()
    model = MagicMock()
    response = AIMessage(content="Controlled response")
    model.invoke.return_value = response
    with monkeypatch.context() as patch:
        patch.setattr(source, attribute, model)
        assert getattr(peer, attribute) is model
        assert getattr(peer, "_resolve_hardware_llm" + suffix)() is model
        assert other_resolve() is untouched
        result = peer.hardware_node({"messages": [HumanMessage(content="Consulta documentacion tecnica" if suffix else "Consulta general")]})
        assert result["messages"][0] is response
        model.invoke.assert_called_once()
    assert resolve() is getattr(peer, "_resolve_hardware_llm" + suffix)() is original
    assert other_resolve() is untouched


@pytest.mark.parametrize("path", [ENGLISH, LEGACY])
@pytest.mark.parametrize("attribute", ["hardware_tools", "tecnico_tools", "hardware_node", "tecnico_node"])
def test_exports_monkeypatch_is_shared_but_graph_keeps_captured_reference(network, monkeypatch, path, attribute):
    graph_module, _ = network
    source, peer = importlib.import_module(path), importlib.import_module(LEGACY if path == ENGLISH else ENGLISH)
    original = getattr(source, attribute)
    captured = graph_module.AGENT_NODES["tecnico"] if attribute.endswith("node") else graph_module.hardware_tools
    replacement = [] if attribute.endswith("tools") else lambda state: {}
    with monkeypatch.context() as patch:
        patch.setattr(source, attribute, replacement)
        assert getattr(peer, attribute) is replacement
        assert (graph_module.AGENT_NODES["tecnico"] if attribute.endswith("node") else graph_module.hardware_tools) is captured
    assert getattr(source, attribute) is getattr(peer, attribute) is original


@pytest.mark.parametrize("path", [ENGLISH, LEGACY])
@pytest.mark.parametrize("legacy_names", [False, True])
def test_rag_then_normal_resume_preserves_models_handoff_and_ids(network, monkeypatch, path, legacy_names):
    graph_module, controls = network
    agent = importlib.import_module(path)
    normal, rag = MagicMock(), MagicMock()
    rag.invoke.return_value = AIMessage(content="", id="rag-event", tool_calls=[dict(
        name="consultar_base_conocimiento", args={"consulta": "Documento fixture"}, id="rag-call")])
    name = "transferir_a_software" if legacy_names else "transfer_to_software"
    normal.invoke.return_value = AIMessage(content="", id="handoff-event", tool_calls=[dict(
        name=name, args={"motivo" if legacy_names else "reason": "Evaluar"}, id="handoff-call")])
    monkeypatch.setattr(agent, "tecnico_llm" if legacy_names else "hardware_llm", normal)
    monkeypatch.setattr(agent, "tecnico_llm_rag" if legacy_names else "hardware_llm_rag", rag)
    saver = MemorySaver()
    config = {"configurable": {"thread_id": "hardware-rag-module"}}
    graph_module.build_graph(checkpointer=saver).update_state(config,
        dict(messages=[HumanMessage(content="Consulta documentacion tecnica", id="human")], current_agent="tecnico",
             request_revision=2, handoff_count=0, handoff_history=[], handoff_records=[]), as_node="preparar_turno")
    graph = graph_module.build_graph(checkpointer=saver)
    first = graph.invoke(None, config, interrupt_after=["auditar_tecnico"])
    rag.invoke.assert_called_once()
    normal.invoke.assert_not_called()
    assert controls["rag_calls"] == ["Documento fixture"]
    result = graph.invoke(None, config, interrupt_after=["auditar_tecnico"])
    normal.invoke.assert_called_once()
    rag.invoke.assert_called_once()
    assert controls["rag_calls"] == ["Documento fixture"]
    outputs = [m for m in result["messages"] if isinstance(m, ToolMessage)]
    assert [(m.name, m.tool_call_id) for m in outputs] == [("consultar_base_conocimiento", "rag-call"), (name, "handoff-call")]
    assert result["handoff_history"] == [{"origin": "tecnico", "destination": "software"}]
    assert result["handoff_count"] == 1


@pytest.mark.parametrize("name,key", [("diagnose_issue", "symptom"), ("diagnosticar_problema", "sintoma")])
def test_preliminary_diagnosis_preserves_public_variants_and_call_id(network, name, key):
    graph_module, _ = network
    call = dict(name=name, args={key: "no enciende"}, id="diagnosis")
    event = AIMessage(content="", id="event", tool_calls=[call])
    saver = MemorySaver()
    config = {"configurable": {"thread_id": "hardware-diagnosis"}}
    graph = graph_module.build_graph(checkpointer=saver)
    graph.update_state(config, dict(messages=[HumanMessage(content="Consulta"), event], current_agent="tecnico",
        handoff_history=[], handoff_records=[], handoff_count=0), as_node="tecnico")
    result = graph.invoke(None, config, interrupt_after=["auditar_tecnico"])
    outputs = [m for m in result["messages"] if isinstance(m, ToolMessage)]
    tool = graph.get_graph().nodes["tecnico_tools"].data.tools_by_name[name]
    assert [(m.name, m.tool_call_id) for m in outputs] == [(name, "diagnosis")]
    assert outputs[0].content == tool.invoke(call["args"])
    assert outputs[0].status != "error" and not result.get("diagnosis_id")


@pytest.mark.parametrize("tool_name", ["transfer_to_software", "transferir_a_software"])
def test_checkpoint_resume_observes_english_model_patch_and_historical_calls(network, monkeypatch, tool_name):
    graph_module, _ = network
    agent = importlib.import_module(ENGLISH)
    event = AIMessage(content="", id="event", tool_calls=[dict(name=tool_name,
        args={"reason" if tool_name == "transfer_to_software" else "motivo": "Evaluar"}, id="call")])
    model = MagicMock()
    model.invoke.return_value = event
    monkeypatch.setattr(agent, "hardware_llm", model)
    saver = MemorySaver()
    config = {"configurable": {"thread_id": "hardware-module"}}
    graph_module.build_graph(checkpointer=saver).update_state(config,
        dict(messages=[HumanMessage(content="Consulta general", id="human")], current_agent="tecnico",
             handoff_count=0, handoff_history=[], handoff_records=[], request_revision=2), as_node="preparar_turno")
    result = graph_module.build_graph(checkpointer=saver).invoke(None, config, interrupt_after=["auditar_tecnico"])
    model.invoke.assert_called_once()
    outputs = [m for m in result["messages"] if isinstance(m, ToolMessage)]
    assert [(m.name, m.tool_call_id) for m in outputs] == [(tool_name, "call")]
    assert result["handoff_history"] == [{"origin": "tecnico", "destination": "software"}]
    assert result["handoff_count"] == 1


def test_legacy_file_only_aliases_canonical_implementation():
    import ast
    source = (ROOT / "app/agents/decentralized/tecnico.py").read_text(encoding="utf-8")
    assert not any(isinstance(node, (ast.FunctionDef, ast.ClassDef)) for node in ast.parse(source).body)
    assert '".hardware"' in source
    implementation = ast.parse((ROOT / "app/agents/decentralized/hardware.py").read_text(encoding="utf-8"))
    assert {node.name for node in implementation.body if isinstance(node, ast.FunctionDef)} == {
        "_resolve_hardware_llm", "_resolve_hardware_llm_rag", "hardware_node"}
    calls = [node for node in ast.walk(implementation) if isinstance(node, ast.Call)]
    assert sum(isinstance(node.func, ast.Name) and node.func.id == "ChatGroq" for node in calls) == 1
    assert sum(isinstance(node.func, ast.Attribute) and node.func.attr == "bind_tools" for node in calls) == 2


@pytest.mark.parametrize("path", [ENGLISH, LEGACY])
@pytest.mark.parametrize("suffix", ["", "_rag"])
def test_conflicting_models_do_not_contaminate_other_resolver(network, monkeypatch, path, suffix):
    agent = importlib.import_module(path)
    resolve = getattr(agent, "_resolve_hardware_llm" + suffix)
    other = getattr(agent, "_resolve_hardware_llm" + ("" if suffix else "_rag"))
    original, untouched = resolve(), other()
    first, second = MagicMock(), MagicMock()
    with monkeypatch.context() as patch:
        patch.setattr(agent, "hardware_llm" + suffix, first)
        patch.setattr(agent, "tecnico_llm" + suffix, second)
        with pytest.raises(ValueError, match="Conflicting hardware"):
            resolve()
        assert other() is untouched
        first.invoke.assert_not_called()
        second.invoke.assert_not_called()
    assert resolve() is original and other() is untouched
