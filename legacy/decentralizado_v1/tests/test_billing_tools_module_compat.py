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
CANONICAL = PREFIX + "billing_tools"
LEGACY = PREFIX + "facturacion_tools"
HANDOFFS = ["transferir_a_facturacion", "transferir_a_soporte", "transferir_a_ventas"]
CAPABILITIES = ["consultar_capacidades_financieras", "get_financial_capabilities"]
EXPORTS = HANDOFFS + CAPABILITIES


@pytest.mark.parametrize("first", ["billing_tools", "facturacion_tools"])
@pytest.mark.parametrize("style", ["importlib", "package"])
def test_fresh_import_orders_share_identity_and_single_execution(first, style):
    script = r'''
import importlib, json, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
executions = []
def profile(frame, event, arg):
    if event == "call" and frame.f_code.co_name == "<module>" and Path(frame.f_code.co_filename).name == "billing_tools.py":
        executions.append(frame.f_code.co_filename)
sys.setprofile(profile)
def load(name):
    if sys.argv[3] == "package":
        namespace = {}
        exec("from app.agents.decentralized.tools import " + name, namespace)
        return namespace[name]
    return importlib.import_module("app.agents.decentralized.tools." + name)
one = load(sys.argv[2])
two = load("facturacion_tools" if sys.argv[2] == "billing_tools" else "billing_tools")
from app.agents.decentralized.tools import billing_tools, facturacion_tools
assert one is two is billing_tools is facturacion_tools
assert load("billing_tools") is load("facturacion_tools") is one
assert sys.modules["app.agents.decentralized.tools.billing_tools"] is sys.modules["app.agents.decentralized.tools.facturacion_tools"] is one
assert one.__name__ == one.__spec__.name == "app.agents.decentralized.tools.billing_tools"
assert Path(one.__file__).name == "billing_tools.py"
assert one.get_financial_capabilities.func is one.consultar_capacidades_financieras.func
assert one.get_financial_capabilities.args_schema is one.consultar_capacidades_financieras.args_schema
assert len(executions) == 1
assert not any(name.startswith(("app.database", "app.rag", "langchain_groq", "psycopg")) for name in sys.modules)
sys.setprofile(None)
print(json.dumps({"executions": len(executions)}))
'''
    result = subprocess.run([sys.executable, "-B", "-c", script, str(ROOT), first, style],
                            cwd=ROOT, capture_output=True, text=True, timeout=60, check=True)
    assert json.loads(result.stdout) == {"executions": 1}


@pytest.mark.parametrize("name", EXPORTS)
def test_metadata_decorated_identity_and_frozen_contract(name):
    canonical, legacy = importlib.import_module(CANONICAL), importlib.import_module(LEGACY)
    assert canonical is legacy
    assert canonical.__name__ == canonical.__spec__.name == CANONICAL
    assert Path(canonical.__file__) == ROOT / "app/agents/decentralized/tools/billing_tools.py"
    tool = getattr(canonical, name)
    assert tool is getattr(legacy, name)
    assert tool.name == name
    assert tool.func.__module__ == CANONICAL
    assert tool.func.__globals__ is canonical.__dict__
    assert inspect.getmodule(tool.func) is canonical
    assert inspect.getsourcefile(tool.func) == canonical.__file__
    assert "def " in inspect.getsource(tool.func)
    assert str(inspect.signature(tool.func)) == ("(motivo: str) -> str" if name in HANDOFFS else "() -> dict")
    assert tool.description == ORIGINAL_CONTRACTS[name]["description"]
    assert tool.args_schema.model_json_schema() == ORIGINAL_CONTRACTS[name]["schema"]
    assert tool.tool_call_schema.model_json_schema() == ORIGINAL_CONTRACTS[name]["call_schema"]


@pytest.mark.parametrize("path", [CANONICAL, LEGACY])
@pytest.mark.parametrize("attribute", [*EXPORTS, "_support", "_sales"])
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
@pytest.mark.parametrize("attribute,tool_name,source", [
    ("_support", "transferir_a_soporte", "software_tools"),
    ("_sales", "transferir_a_ventas", "soporte_tools"),
])
def test_dependency_delegation_preserves_arguments_results_and_exceptions(path, attribute, tool_name, source, monkeypatch):
    module = importlib.import_module(path)
    peer = importlib.import_module(LEGACY if path == CANONICAL else CANONICAL)
    original = getattr(module, attribute)
    assert original is getattr(importlib.import_module(PREFIX + source), tool_name)
    replacement = MagicMock()
    replacement.invoke.return_value = "Controlled handoff"
    with monkeypatch.context() as patch:
        patch.setattr(module, attribute, replacement)
        assert getattr(peer, tool_name).invoke({"motivo": " Evaluar "}) == "Controlled handoff"
        replacement.invoke.assert_called_once_with({"motivo": "Evaluar"})
        error = ValueError("Controlled dependency failure")
        replacement.invoke.side_effect = error
        with pytest.raises(ValueError) as captured:
            getattr(peer, tool_name).invoke({"motivo": "Evaluar"})
        assert captured.value is error
    assert getattr(module, attribute) is original


@pytest.mark.parametrize("name", HANDOFFS)
def test_handoff_results_and_existing_validation(name):
    tool = getattr(importlib.import_module(CANONICAL), name)
    assert tool.invoke({"motivo": " Evaluar "}) == "TRANSFERIR_" + name.removeprefix("transferir_a_").upper() + ": Evaluar"
    for reason in ("", " "):
        with pytest.raises(ValueError, match="Motivo obligatorio"):
            tool.invoke({"motivo": reason})
    for args in ({}, {"motivo": None}, {"motivo": 3}):
        with pytest.raises(ValidationError):
            tool.invoke(args)


@pytest.mark.parametrize("name", CAPABILITIES)
def test_capabilities_do_not_enable_writes_or_reconciliation(name):
    module = importlib.import_module(CANONICAL)
    tool = getattr(module, name)
    expected = dict(payment_write_enabled=False, fiscal_integration_available=False,
                    payment_reconciliation_available=False, refund_write_enabled=False)
    result = tool.invoke({})
    assert result == expected
    result["payment_write_enabled"] = True
    assert tool.invoke({}) == expected
    assert module.get_financial_capabilities.func is module.consultar_capacidades_financieras.func
    assert module.get_financial_capabilities.args_schema is module.consultar_capacidades_financieras.args_schema


def test_agent_wrappers_and_toolnode_preserve_captured_objects(network, monkeypatch):
    graph_module, _ = network
    module = importlib.import_module(CANONICAL)
    agent = importlib.import_module("app.agents.decentralized.billing")
    wrappers = importlib.import_module(PREFIX + "billing_handoff_tools")
    support = importlib.import_module(PREFIX + "support_handoff_tools")
    sales = importlib.import_module(PREFIX + "sales_handoff_tools")
    assert wrappers._support is module.transferir_a_soporte
    assert wrappers._sales is module.transferir_a_ventas
    assert support._billing is sales._billing is module.transferir_a_facturacion
    assert agent.billing_tools is agent.facturacion_tools is graph_module.billing_tools
    assert [tool.name for tool in agent.billing_tools] == ["transfer_to_support", "transfer_to_sales", "get_financial_capabilities", "transfer_to_logistics"]
    assert agent.billing_tools[2] is module.get_financial_capabilities
    registered = graph_module.build_graph().get_graph().nodes["facturacion_tools"].data.tools_by_name
    assert list(registered) == ["transfer_to_support", "transfer_to_sales", "get_financial_capabilities", "transfer_to_logistics",
        "transferir_a_soporte", "transferir_a_ventas", "transferir_a_logistica", "consultar_capacidades_financieras"]
    assert registered["get_financial_capabilities"] is module.get_financial_capabilities
    assert registered["consultar_capacidades_financieras"] is graph_module.consultar_capacidades_financieras is module.consultar_capacidades_financieras
    captured = module.transferir_a_soporte
    with monkeypatch.context() as patch:
        patch.setattr(module, "transferir_a_soporte", MagicMock())
        assert wrappers._support is registered["transferir_a_soporte"] is captured
    assert module.transferir_a_soporte is captured


@pytest.mark.parametrize("destination", ["soporte", "ventas"])
@pytest.mark.parametrize("style", ["english", "legacy", "mixed"])
def test_checkpoint_handoffs_preserve_ids_audit_without_financial_results(network, destination, style):
    graph_module, _ = network
    english = "transfer_to_" + ("support" if destination == "soporte" else "sales")
    legacy = "transferir_a_" + destination
    names = [english, legacy] if style == "mixed" else [english if style == "english" else legacy]
    calls = [dict(name=name, args={"reason" if name == english else "motivo": " Evaluar "}, id="call-" + str(index))
             for index, name in enumerate(names)]
    event = AIMessage(content="", id="event", tool_calls=calls)
    before = deepcopy(event)
    saver = MemorySaver()
    config = {"configurable": {"thread_id": "billing-tools-module"}}
    graph_module.build_graph(checkpointer=saver).update_state(config, dict(
        messages=[HumanMessage(content="Consulta"), event], current_agent="facturacion",
        handoff_count=0, handoff_history=[], handoff_records=[]), as_node="facturacion")
    result = graph_module.build_graph(checkpointer=saver).invoke(None, config, interrupt_after=["auditar_facturacion"])
    outputs = [message for message in result["messages"] if isinstance(message, ToolMessage)]
    assert [(message.name, message.tool_call_id) for message in outputs] == [(call["name"], call["id"]) for call in calls]
    assert all(message.status != "error" for message in outputs)
    assert result["handoff_history"] == [{"origin": "facturacion", "destination": destination}]
    assert result["handoff_count"] == len(result["handoff_records"]) == 1
    assert result["handoff_records"][0]["reason"] == "Evaluar"
    assert event == before
    assert not any(result.get(key) for key in ("payment_id", "payment_code", "refund_id"))


def test_legacy_shim_and_single_canonical_ast():
    legacy = (ROOT / "app/agents/decentralized/tools/facturacion_tools.py").read_text(encoding="utf-8")
    assert '".billing_tools"' in legacy
    assert not any(isinstance(node, (ast.FunctionDef, ast.ClassDef)) for node in ast.parse(legacy).body)
    tree = ast.parse((ROOT / "app/agents/decentralized/tools/billing_tools.py").read_text(encoding="utf-8"))
    assert {node.name for node in tree.body if isinstance(node, ast.FunctionDef)} == {
        "transferir_a_facturacion", "transferir_a_soporte", "transferir_a_ventas", "consultar_capacidades_financieras"}


ORIGINAL_CONTRACTS = {'transferir_a_facturacion': {'description': 'Consulta financiera; no crea pagos ni acredita aceptación o '
                                             'pago recibido.',
                              'schema': {'description': 'Consulta financiera; no crea pagos ni acredita '
                                                        'aceptación o pago recibido.',
                                         'properties': {'motivo': {'title': 'Motivo', 'type': 'string'}},
                                         'required': ['motivo'],
                                         'title': 'transferir_a_facturacion',
                                         'type': 'object'},
                              'call_schema': {'description': 'Consulta financiera; no crea pagos ni acredita '
                                                             'aceptación o pago recibido.',
                                              'properties': {'motivo': {'title': 'Motivo', 'type': 'string'}},
                                              'required': ['motivo'],
                                              'title': 'transferir_a_facturacion',
                                              'type': 'object'}},
 'transferir_a_soporte': {'description': 'Solicita atención administrativa sin confirmar un pago ni emitir '
                                         'factura.',
                          'schema': {'description': 'Solicita atención administrativa sin confirmar un pago '
                                                    'ni emitir factura.',
                                     'properties': {'motivo': {'title': 'Motivo', 'type': 'string'}},
                                     'required': ['motivo'],
                                     'title': 'transferir_a_soporte',
                                     'type': 'object'},
                          'call_schema': {'description': 'Solicita atención administrativa sin confirmar un '
                                                         'pago ni emitir factura.',
                                          'properties': {'motivo': {'title': 'Motivo', 'type': 'string'}},
                                          'required': ['motivo'],
                                          'title': 'transferir_a_soporte',
                                          'type': 'object'}},
 'transferir_a_ventas': {'description': 'Devuelve una propuesta pendiente o incompatible a Ventas.',
                         'schema': {'description': 'Devuelve una propuesta pendiente o incompatible a '
                                                   'Ventas.',
                                    'properties': {'motivo': {'title': 'Motivo', 'type': 'string'}},
                                    'required': ['motivo'],
                                    'title': 'transferir_a_ventas',
                                    'type': 'object'},
                         'call_schema': {'description': 'Devuelve una propuesta pendiente o incompatible a '
                                                        'Ventas.',
                                         'properties': {'motivo': {'title': 'Motivo', 'type': 'string'}},
                                         'required': ['motivo'],
                                         'title': 'transferir_a_ventas',
                                         'type': 'object'}},
 'consultar_capacidades_financieras': {'description': 'Informa integraciones financieras habilitadas, sin '
                                                      'ejecutar operaciones.',
                                       'schema': {'description': 'Informa integraciones financieras '
                                                                 'habilitadas, sin ejecutar operaciones.',
                                                  'properties': {},
                                                  'title': 'consultar_capacidades_financieras',
                                                  'type': 'object'},
                                       'call_schema': {'description': 'Informa integraciones financieras '
                                                                      'habilitadas, sin ejecutar '
                                                                      'operaciones.',
                                                       'properties': {},
                                                       'title': 'consultar_capacidades_financieras',
                                                       'type': 'object'}},
 'get_financial_capabilities': {'description': 'Informa integraciones financieras habilitadas, sin ejecutar '
                                               'operaciones.',
                                'schema': {'description': 'Informa integraciones financieras habilitadas, '
                                                          'sin ejecutar operaciones.',
                                           'properties': {},
                                           'title': 'consultar_capacidades_financieras',
                                           'type': 'object'},
                                'call_schema': {'description': 'Informa integraciones financieras '
                                                               'habilitadas, sin ejecutar operaciones.',
                                                'properties': {},
                                                'title': 'get_financial_capabilities',
                                                'type': 'object'}}}
