import ast
from copy import deepcopy
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
from pydantic import ValidationError

from test_software_e2e import network


ROOT = Path(__file__).resolve().parents[1]
CANONICAL = "app.agents.decentralized.tools.logistics_tools"
LEGACY = "app.agents.decentralized.tools.logistica_tools"
EXPORTS = ["transferir_a_logistica", "transferir_a_soporte"]


@pytest.mark.parametrize("first", ["logistics_tools", "logistica_tools"])
@pytest.mark.parametrize("style", ["importlib", "package"])
def test_fresh_import_orders_share_module_and_execute_once(first, style):
    script = r'''
import importlib, json, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
executions = []
def profile(frame, event, arg):
    if event == "call" and frame.f_code.co_name == "<module>" and Path(frame.f_code.co_filename).name == "logistics_tools.py":
        executions.append(frame.f_code.co_filename)
sys.setprofile(profile)
def load(name):
    if sys.argv[3] == "package":
        namespace = {}
        exec("from app.agents.decentralized.tools import " + name, namespace)
        return namespace[name]
    return importlib.import_module("app.agents.decentralized.tools." + name)
one = load(sys.argv[2])
two = load("logistica_tools" if sys.argv[2] == "logistics_tools" else "logistics_tools")
from app.agents.decentralized.tools import logistics_tools, logistica_tools
assert one is two is logistics_tools is logistica_tools
assert load("logistics_tools") is load("logistica_tools") is one
assert sys.modules["app.agents.decentralized.tools.logistics_tools"] is sys.modules["app.agents.decentralized.tools.logistica_tools"] is one
assert one.__name__ == one.__spec__.name == "app.agents.decentralized.tools.logistics_tools"
assert Path(one.__file__).name == "logistics_tools.py"
assert len(executions) == 1
assert not any(name.startswith(("app.database", "app.rag", "langchain_groq", "psycopg")) for name in sys.modules)
sys.setprofile(None)
print(json.dumps({"executions": len(executions)}))
'''
    result = subprocess.run([sys.executable, "-B", "-c", script, str(ROOT), first, style],
                            cwd=ROOT, capture_output=True, text=True, timeout=60, check=True)
    assert json.loads(result.stdout) == {"executions": 1}


@pytest.mark.parametrize("name", EXPORTS)
def test_decorated_identity_metadata_signature_and_frozen_schema(name):
    canonical, legacy = importlib.import_module(CANONICAL), importlib.import_module(LEGACY)
    assert canonical is legacy
    assert canonical.__name__ == canonical.__spec__.name == CANONICAL
    assert Path(canonical.__file__) == ROOT / "app/agents/decentralized/tools/logistics_tools.py"
    tool = getattr(canonical, name)
    assert tool is getattr(legacy, name)
    assert tool.name == name
    assert tool.func.__module__ == CANONICAL
    assert tool.func.__globals__ is canonical.__dict__
    assert inspect.getmodule(tool.func) is canonical
    assert inspect.getsourcefile(tool.func) == canonical.__file__
    assert "def " + name in inspect.getsource(tool.func)
    assert str(inspect.signature(tool.func)) == "(motivo: str) -> str"
    assert tool.description == ORIGINAL_CONTRACTS[name]["description"]
    assert tool.args_schema.model_json_schema() == ORIGINAL_CONTRACTS[name]["schema"]
    assert tool.tool_call_schema.model_json_schema() == ORIGINAL_CONTRACTS[name]["call_schema"]


@pytest.mark.parametrize("path", [CANONICAL, LEGACY])
@pytest.mark.parametrize("attribute", [*EXPORTS, "_support"])
def test_bidirectional_monkeypatch_and_restoration(path, attribute, monkeypatch):
    module = importlib.import_module(path)
    peer = importlib.import_module(LEGACY if path == CANONICAL else CANONICAL)
    original = getattr(module, attribute)
    with monkeypatch.context() as patch:
        replacement = MagicMock()
        patch.setattr(module, attribute, replacement)
        assert getattr(peer, attribute) is replacement
    assert getattr(module, attribute) is getattr(peer, attribute) is original


@pytest.mark.parametrize("path", [CANONICAL, LEGACY])
def test_software_tool_delegation_preserves_arguments_results_and_errors(path, monkeypatch):
    module = importlib.import_module(path)
    peer = importlib.import_module(LEGACY if path == CANONICAL else CANONICAL)
    software = importlib.import_module("app.agents.decentralized.tools.software_tools")
    assert module._support is software.transferir_a_soporte
    assert peer.transferir_a_soporte.invoke({"motivo": " Evaluar "}) == "TRANSFERIR_SOPORTE: Evaluar"
    replacement = MagicMock()
    replacement.invoke.return_value = "Controlled support response"
    with monkeypatch.context() as patch:
        patch.setattr(module, "_support", replacement)
        assert peer.transferir_a_soporte.invoke({"motivo": " Evaluar "}) == "Controlled support response"
        replacement.invoke.assert_called_once_with({"motivo": "Evaluar"})
        error = ValueError("Controlled delegation failure")
        replacement.invoke.side_effect = error
        with pytest.raises(ValueError) as captured:
            peer.transferir_a_soporte.invoke({"motivo": "Evaluar"})
        assert captured.value is error
    assert module._support is software.transferir_a_soporte


@pytest.mark.parametrize("name", EXPORTS)
def test_results_and_invalid_reasons_keep_existing_contract(name):
    tool = getattr(importlib.import_module(CANONICAL), name)
    destination = "LOGISTICA" if name == "transferir_a_logistica" else "SOPORTE"
    assert tool.invoke({"motivo": " Evaluar "}) == "TRANSFERIR_" + destination + ": Evaluar"
    for reason in ("", " "):
        with pytest.raises(ValueError, match="Motivo obligatorio"):
            tool.invoke({"motivo": reason})
    for args in ({}, {"motivo": None}, {"motivo": 3}):
        with pytest.raises(ValidationError):
            tool.invoke(args)


def test_warranty_reexports_wrappers_and_registries_keep_captured_objects(network, monkeypatch):
    graph_module, _ = network
    module = importlib.import_module(CANONICAL)
    warranty = importlib.import_module("app.agents.decentralized.tools.garantia_tools")
    warranty_wrappers = importlib.import_module("app.agents.decentralized.tools.warranty_handoff_tools")
    logistics_wrappers = importlib.import_module("app.agents.decentralized.tools.logistics_handoff_tools")
    agent = importlib.import_module("app.agents.decentralized.logistics")
    assert warranty.garantia_tools == [module.transferir_a_logistica, module.transferir_a_soporte]
    assert warranty.transferir_a_logistica is warranty_wrappers._logistics is module.transferir_a_logistica
    assert warranty.transferir_a_soporte is warranty_wrappers._support is logistics_wrappers._support is module.transferir_a_soporte
    for prefix in ("software", "hardware", "billing", "support"):
        wrappers = importlib.import_module("app.agents.decentralized.tools." + prefix + "_handoff_tools")
        assert wrappers._logistics is module.transferir_a_logistica
    assert agent.logistics_tools is agent.logistica_tools is graph_module.logistics_tools
    assert [tool.name for tool in agent.logistics_tools] == ["transfer_to_support"]
    graph = graph_module.build_graph().get_graph()
    registered = graph.nodes["logistica_tools"].data.tools_by_name
    assert set(registered) == {"transfer_to_support", "transferir_a_soporte"}
    assert registered["transferir_a_soporte"] is module.transferir_a_soporte
    assert graph.nodes["garantia_tools"].data.tools_by_name["transferir_a_logistica"] is module.transferir_a_logistica
    captured = module.transferir_a_soporte
    with monkeypatch.context() as patch:
        patch.setattr(module, "transferir_a_soporte", MagicMock())
        assert warranty.transferir_a_soporte is logistics_wrappers._support is registered["transferir_a_soporte"] is captured
    assert module.transferir_a_soporte is captured


@pytest.mark.parametrize("origin,destination", [("logistica", "soporte"), ("garantia", "soporte"),
    ("garantia", "logistica"), ("software", "logistica")])
@pytest.mark.parametrize("style", ["english", "legacy", "mixed"])
def test_checkpoint_batches_keep_destinations_reasons_and_ids(network, origin, destination, style):
    graph_module, _ = network
    english = "transfer_to_" + ("support" if destination == "soporte" else "logistics")
    legacy = "transferir_a_" + destination
    names = [english, legacy] if style == "mixed" else [english if style == "english" else legacy]
    calls = [dict(name=name, args={"reason" if name == english else "motivo": " Evaluar "}, id="call-" + str(index))
             for index, name in enumerate(names)]
    event = AIMessage(content="", id="event", tool_calls=calls)
    before = deepcopy(event)
    saver = MemorySaver()
    config = {"configurable": {"thread_id": "logistics-tools-module"}}
    graph_module.build_graph(checkpointer=saver).update_state(config, dict(
        messages=[HumanMessage(content="Consulta"), event], current_agent=origin,
        handoff_count=0, handoff_history=[], handoff_records=[]), as_node=origin)
    result = graph_module.build_graph(checkpointer=saver).invoke(None, config, interrupt_after=["auditar_" + origin])
    outputs = [message for message in result["messages"] if isinstance(message, ToolMessage)]
    assert [(message.name, message.tool_call_id) for message in outputs] == [(call["name"], call["id"]) for call in calls]
    assert all(message.status != "error" for message in outputs)
    assert result["handoff_history"] == [{"origin": origin, "destination": destination}]
    assert result["handoff_count"] == len(result["handoff_records"]) == 1
    assert result["handoff_records"][0]["reason"] == "Evaluar"
    assert event == before
    assert not any(result.get(key) for key in ("payment_id", "logistics_record_id", "warranty_claim_id"))


def test_legacy_shim_and_single_canonical_ast():
    legacy = (ROOT / "app/agents/decentralized/tools/logistica_tools.py").read_text(encoding="utf-8")
    assert '".logistics_tools"' in legacy
    assert not any(isinstance(node, (ast.FunctionDef, ast.ClassDef)) for node in ast.parse(legacy).body)
    tree = ast.parse((ROOT / "app/agents/decentralized/tools/logistics_tools.py").read_text(encoding="utf-8"))
    assert {node.name for node in tree.body if isinstance(node, ast.FunctionDef)} == {
        "transferir_a_logistica", "transferir_a_soporte"}


ORIGINAL_CONTRACTS = {'transferir_a_logistica': {'description': 'Solicita coordinación; Logística revalida ticket y '
                                           'precondiciones persistidas.',
                            'schema': {'description': 'Solicita coordinación; Logística revalida ticket y '
                                                      'precondiciones persistidas.',
                                       'properties': {'motivo': {'title': 'Motivo', 'type': 'string'}},
                                       'required': ['motivo'],
                                       'title': 'transferir_a_logistica',
                                       'type': 'object'},
                            'call_schema': {'description': 'Solicita coordinación; Logística revalida ticket '
                                                           'y precondiciones persistidas.',
                                            'properties': {'motivo': {'title': 'Motivo', 'type': 'string'}},
                                            'required': ['motivo'],
                                            'title': 'transferir_a_logistica',
                                            'type': 'object'}},
 'transferir_a_soporte': {'description': 'Devuelve atención informativa sin confirmar recepción, despacho o '
                                         'garantía.',
                          'schema': {'description': 'Devuelve atención informativa sin confirmar recepción, '
                                                    'despacho o garantía.',
                                     'properties': {'motivo': {'title': 'Motivo', 'type': 'string'}},
                                     'required': ['motivo'],
                                     'title': 'transferir_a_soporte',
                                     'type': 'object'},
                          'call_schema': {'description': 'Devuelve atención informativa sin confirmar '
                                                         'recepción, despacho o garantía.',
                                          'properties': {'motivo': {'title': 'Motivo', 'type': 'string'}},
                                          'required': ['motivo'],
                                          'title': 'transferir_a_soporte',
                                          'type': 'object'}}}
