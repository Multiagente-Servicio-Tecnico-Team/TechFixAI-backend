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
PREFIX = "app.agents.decentralized.tools."
CANONICAL = PREFIX + "warranty_tools"
LEGACY = PREFIX + "garantia_tools"
EXPORTS = ["transferir_a_garantia", "transferir_a_logistica", "transferir_a_soporte"]


@pytest.mark.parametrize("first", ["warranty_tools", "garantia_tools"])
@pytest.mark.parametrize("style", ["importlib", "package"])
@pytest.mark.parametrize("logistics_first", [False, True])
def test_fresh_import_orders_preserve_reexports_and_single_execution(first, style, logistics_first):
    script = r'''
import importlib, json, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
executions = []
def profile(frame, event, arg):
    if event == "call" and frame.f_code.co_name == "<module>":
        filename = Path(frame.f_code.co_filename).name
        if filename in {"warranty_tools.py", "logistics_tools.py"}:
            executions.append(filename)
sys.setprofile(profile)
if sys.argv[4] == "logistics-first":
    importlib.import_module("app.agents.decentralized.tools.logistics_tools")
def load(name):
    if sys.argv[3] == "package":
        namespace = {}
        exec("from app.agents.decentralized.tools import " + name, namespace)
        return namespace[name]
    return importlib.import_module("app.agents.decentralized.tools." + name)
one = load(sys.argv[2])
two = load("garantia_tools" if sys.argv[2] == "warranty_tools" else "warranty_tools")
from app.agents.decentralized.tools import warranty_tools, garantia_tools, logistics_tools, logistica_tools
assert one is two is warranty_tools is garantia_tools
assert load("warranty_tools") is load("garantia_tools") is one
assert logistics_tools is logistica_tools
assert one.__name__ == one.__spec__.name == "app.agents.decentralized.tools.warranty_tools"
assert Path(one.__file__).name == "warranty_tools.py"
assert one.transferir_a_logistica is logistics_tools.transferir_a_logistica
assert one.transferir_a_soporte is logistics_tools.transferir_a_soporte
assert one.garantia_tools is two.garantia_tools
assert one.garantia_tools == [logistics_tools.transferir_a_logistica, logistics_tools.transferir_a_soporte]
wrappers = importlib.import_module("app.agents.decentralized.tools.warranty_handoff_tools")
assert wrappers._logistics is one.transferir_a_logistica
assert wrappers._support is one.transferir_a_soporte
assert executions.count("warranty_tools.py") == executions.count("logistics_tools.py") == 1
assert not any(name.startswith(("app.database", "app.rag", "langchain_groq", "psycopg")) for name in sys.modules)
sys.setprofile(None)
print(json.dumps({"warranty": executions.count("warranty_tools.py"), "logistics": executions.count("logistics_tools.py")}))
'''
    result = subprocess.run([sys.executable, "-B", "-c", script, str(ROOT), first, style,
                             "logistics-first" if logistics_first else "warranty-first"],
                            cwd=ROOT, capture_output=True, text=True, timeout=60, check=True)
    assert json.loads(result.stdout) == {"warranty": 1, "logistics": 1}


@pytest.mark.parametrize("name", EXPORTS)
def test_metadata_distinguishes_owned_and_reexported_tools_and_frozen_contract(name):
    canonical, legacy = importlib.import_module(CANONICAL), importlib.import_module(LEGACY)
    assert canonical is legacy
    assert canonical.__name__ == canonical.__spec__.name == CANONICAL
    assert Path(canonical.__file__) == ROOT / "app/agents/decentralized/tools/warranty_tools.py"
    tool = getattr(canonical, name)
    assert tool is getattr(legacy, name)
    assert tool.name == name
    origin = canonical if name == "transferir_a_garantia" else importlib.import_module(PREFIX + "logistics_tools")
    assert tool.func.__module__ == origin.__name__
    assert tool.func.__globals__ is origin.__dict__
    assert inspect.getmodule(tool.func) is origin
    assert inspect.getsourcefile(tool.func) == origin.__file__
    assert "def " + name in inspect.getsource(tool.func)
    assert str(inspect.signature(tool.func)) == "(motivo: str) -> str"
    assert tool.description == ORIGINAL_CONTRACTS[name]["description"]
    assert tool.args_schema.model_json_schema() == ORIGINAL_CONTRACTS[name]["schema"]
    assert tool.tool_call_schema.model_json_schema() == ORIGINAL_CONTRACTS[name]["call_schema"]


@pytest.mark.parametrize("path", [CANONICAL, LEGACY])
@pytest.mark.parametrize("attribute", [*EXPORTS, "garantia_tools"])
def test_bidirectional_monkeypatch_and_restoration(path, attribute, monkeypatch):
    module = importlib.import_module(path)
    peer = importlib.import_module(LEGACY if path == CANONICAL else CANONICAL)
    original = getattr(module, attribute)
    with monkeypatch.context() as patch:
        replacement = [] if attribute == "garantia_tools" else MagicMock()
        patch.setattr(module, attribute, replacement)
        assert getattr(peer, attribute) is replacement
    assert getattr(module, attribute) is getattr(peer, attribute) is original


@pytest.mark.parametrize("path", [CANONICAL, LEGACY])
def test_reexport_uses_origin_globals_without_rebinding_captured_references(path, monkeypatch):
    module = importlib.import_module(path)
    logistics = importlib.import_module(PREFIX + "logistics_tools")
    wrappers = importlib.import_module(PREFIX + "warranty_handoff_tools")
    original = module.transferir_a_soporte
    assert original is logistics.transferir_a_soporte is wrappers._support
    replacement = MagicMock()
    with monkeypatch.context() as patch:
        patch.setattr(module, "transferir_a_soporte", replacement)
        assert wrappers._support is logistics.transferir_a_soporte is module.garantia_tools[1] is original
    support = MagicMock()
    support.invoke.return_value = "Controlled support result"
    with monkeypatch.context() as patch:
        patch.setattr(logistics, "_support", support)
        assert module.transferir_a_soporte.invoke({"motivo": " Evaluar "}) == "Controlled support result"
        support.invoke.assert_called_once_with({"motivo": "Evaluar"})
    assert module.transferir_a_soporte is wrappers._support is logistics.transferir_a_soporte is original


@pytest.mark.parametrize("name", EXPORTS)
def test_results_validation_and_expected_errors(name):
    tool = getattr(importlib.import_module(CANONICAL), name)
    destination = name.removeprefix("transferir_a_").upper()
    assert tool.invoke({"motivo": " Evaluar "}) == "TRANSFERIR_" + destination + ": Evaluar"
    for reason in ("", " "):
        with pytest.raises(ValueError, match="Motivo obligatorio"):
            tool.invoke({"motivo": reason})
    for args in ({}, {"motivo": None}, {"motivo": 3}):
        with pytest.raises(ValidationError):
            tool.invoke(args)


def test_legacy_list_and_active_wrapper_registry_remain_distinct_and_shared(network, monkeypatch):
    graph_module, _ = network
    module = importlib.import_module(CANONICAL)
    legacy = importlib.import_module(LEGACY)
    logistics = importlib.import_module(PREFIX + "logistics_tools")
    wrappers = importlib.import_module(PREFIX + "warranty_handoff_tools")
    support = importlib.import_module(PREFIX + "support_handoff_tools")
    agent = importlib.import_module("app.agents.decentralized.warranty")
    assert support._warranty is module.transferir_a_garantia
    assert module.garantia_tools is legacy.garantia_tools
    assert module.garantia_tools == [logistics.transferir_a_logistica, logistics.transferir_a_soporte]
    assert wrappers.legacy_handoff_tools == module.garantia_tools
    assert wrappers._logistics is module.garantia_tools[0]
    assert wrappers._support is module.garantia_tools[1]
    assert agent.warranty_tools is agent.garantia_tools is graph_module.warranty_tools is wrappers.warranty_handoff_tools
    assert agent.warranty_tools is not module.garantia_tools
    assert [tool.name for tool in agent.warranty_tools] == ["transfer_to_logistics", "transfer_to_support"]
    registered = graph_module.build_graph().get_graph().nodes["garantia_tools"].data.tools_by_name
    assert list(registered) == ["transfer_to_logistics", "transfer_to_support", "transferir_a_logistica", "transferir_a_soporte"]
    assert registered["transferir_a_logistica"] is module.transferir_a_logistica
    assert registered["transferir_a_soporte"] is module.transferir_a_soporte
    captured = module.transferir_a_garantia
    with monkeypatch.context() as patch:
        patch.setattr(module, "transferir_a_garantia", MagicMock())
        assert support._warranty is captured
    assert module.transferir_a_garantia is captured


@pytest.mark.parametrize("destination", ["logistica", "soporte"])
@pytest.mark.parametrize("style", ["english", "legacy", "mixed"])
def test_checkpoint_reexports_keep_handoffs_ids_and_audit(network, destination, style):
    graph_module, _ = network
    english = "transfer_to_" + ("logistics" if destination == "logistica" else "support")
    legacy = "transferir_a_" + destination
    names = [english, legacy] if style == "mixed" else [english if style == "english" else legacy]
    calls = [dict(name=name, args={"reason" if name == english else "motivo": " Evaluar "}, id="call-" + str(index))
             for index, name in enumerate(names)]
    event = AIMessage(content="", id="event", tool_calls=calls)
    before = deepcopy(event)
    config = {"configurable": {"thread_id": "warranty-tools-module"}}
    saver = MemorySaver()
    graph_module.build_graph(checkpointer=saver).update_state(config, dict(
        messages=[HumanMessage(content="Consulta"), event], current_agent="garantia",
        handoff_count=0, handoff_history=[], handoff_records=[]), as_node="garantia")
    result = graph_module.build_graph(checkpointer=saver).invoke(None, config, interrupt_after=["auditar_garantia"])
    outputs = [message for message in result["messages"] if isinstance(message, ToolMessage)]
    assert [(message.name, message.tool_call_id) for message in outputs] == [(call["name"], call["id"]) for call in calls]
    assert all(message.status != "error" for message in outputs)
    assert result["handoff_history"] == [{"origin": "garantia", "destination": destination}]
    assert result["handoff_count"] == len(result["handoff_records"]) == 1
    assert result["handoff_records"][0]["reason"] == "Evaluar"
    assert event == before
    assert not any(result.get(key) for key in ("payment_id", "logistics_record_id", "warranty_claim_id"))


def test_legacy_shim_and_canonical_ast_keep_imported_tools_imported():
    legacy = (ROOT / "app/agents/decentralized/tools/garantia_tools.py").read_text(encoding="utf-8")
    assert '".warranty_tools"' in legacy
    assert not any(isinstance(node, (ast.FunctionDef, ast.ClassDef)) for node in ast.parse(legacy).body)
    tree = ast.parse((ROOT / "app/agents/decentralized/tools/warranty_tools.py").read_text(encoding="utf-8"))
    assert {node.name for node in tree.body if isinstance(node, ast.FunctionDef)} == {"transferir_a_garantia"}
    imported = next(node for node in tree.body if isinstance(node, ast.ImportFrom) and node.module.endswith("logistica_tools"))
    assert [alias.name for alias in imported.names] == ["transferir_a_logistica", "transferir_a_soporte"]


ORIGINAL_CONTRACTS = {'transferir_a_garantia': {'description': 'Consulta o revisión de garantía; el destino verifica propiedad y '
                                          'datos reales.',
                           'schema': {'description': 'Consulta o revisión de garantía; el destino verifica '
                                                     'propiedad y datos reales.',
                                      'properties': {'motivo': {'title': 'Motivo', 'type': 'string'}},
                                      'required': ['motivo'],
                                      'title': 'transferir_a_garantia',
                                      'type': 'object'},
                           'call_schema': {'description': 'Consulta o revisión de garantía; el destino '
                                                          'verifica propiedad y datos reales.',
                                           'properties': {'motivo': {'title': 'Motivo', 'type': 'string'}},
                                           'required': ['motivo'],
                                           'title': 'transferir_a_garantia',
                                           'type': 'object'}},
 'transferir_a_logistica': {'description': 'Solicita coordinación; Logística revalida ticket y '
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
