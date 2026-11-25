import ast
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
CANONICAL = "app.agents.decentralized.tools.sales_tools"
LEGACY = "app.agents.decentralized.tools.ventas_tools"
EXPORTS = ["solicitar_inventario", "generar_cotizacion", "identify_quote_service", "transferir_a_tecnico"]


@pytest.mark.parametrize("first", ["sales_tools", "ventas_tools"])
@pytest.mark.parametrize("style", ["importlib", "package"])
def test_fresh_import_orders_share_identity_and_execute_once(first, style):
    script = r'''
import importlib, json, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
executions = []
def profile(frame, event, arg):
    if event == "call" and frame.f_code.co_name == "<module>" and Path(frame.f_code.co_filename).name == "sales_tools.py":
        executions.append(frame.f_code.co_filename)
sys.setprofile(profile)
def load(name):
    if sys.argv[3] == "package":
        namespace = {}
        exec("from app.agents.decentralized.tools import " + name, namespace)
        return namespace[name]
    return importlib.import_module("app.agents.decentralized.tools." + name)
one = load(sys.argv[2])
two = load("ventas_tools" if sys.argv[2] == "sales_tools" else "sales_tools")
from app.agents.decentralized.tools import sales_tools, ventas_tools
assert one is two is sales_tools is ventas_tools
assert load("sales_tools") is load("ventas_tools") is one
assert sys.modules["app.agents.decentralized.tools.sales_tools"] is sys.modules["app.agents.decentralized.tools.ventas_tools"] is one
assert one.__name__ == one.__spec__.name == "app.agents.decentralized.tools.sales_tools"
assert Path(one.__file__).name == "sales_tools.py"
assert one.normalize_service is one.normalizar_servicio
assert len(executions) == 1
assert not any(name.startswith(("app.database", "app.rag", "langchain_groq", "psycopg")) for name in sys.modules)
sys.setprofile(None)
print(json.dumps({"executions": len(executions)}))
'''
    result = subprocess.run([sys.executable, "-B", "-c", script, str(ROOT), first, style],
                            cwd=ROOT, capture_output=True, text=True, timeout=60, check=True)
    assert json.loads(result.stdout) == {"executions": 1}


@pytest.mark.parametrize("name", EXPORTS)
def test_decorated_identity_metadata_and_frozen_contract(name):
    canonical, legacy = importlib.import_module(CANONICAL), importlib.import_module(LEGACY)
    assert canonical is legacy
    assert canonical.__name__ == canonical.__spec__.name == CANONICAL
    assert Path(canonical.__file__) == ROOT / "app/agents/decentralized/tools/sales_tools.py"
    tool = getattr(canonical, name)
    assert tool is getattr(legacy, name)
    assert tool.name == name
    assert tool.func.__module__ == CANONICAL
    assert tool.func.__globals__ is canonical.__dict__
    assert inspect.getmodule(tool.func) is canonical
    assert inspect.getsourcefile(tool.func) == canonical.__file__
    assert "def " in inspect.getsource(tool.func)
    assert tool.description == ORIGINAL_CONTRACTS[name]["description"]
    assert tool.args_schema.model_json_schema() == ORIGINAL_CONTRACTS[name]["schema"]
    assert tool.tool_call_schema.model_json_schema() == ORIGINAL_CONTRACTS[name]["call_schema"]


@pytest.mark.parametrize("path", [CANONICAL, LEGACY])
def test_normalization_aliases_signature_defaults_and_errors(path):
    module = importlib.import_module(path)
    assert module.normalize_service is module.normalizar_servicio
    function = module.normalize_service
    parameters = inspect.signature(function).parameters
    assert list(parameters) == ["service", "servicio"]
    assert parameters["service"].default is parameters["servicio"].default is module._MISSING_SERVICE
    assert parameters["servicio"].kind == inspect.Parameter.KEYWORD_ONLY
    for args in (("  INSTALACIÓN  ",),):
        assert function(*args) == "instalacion"
    assert function(service="Reparación") == function(servicio="Reparación") == "reparacion"
    with pytest.raises(TypeError, match="Missing service"):
        function()
    with pytest.raises(TypeError, match="Specify either service or servicio, not both"):
        function(service="same", servicio="same")
    assert inspect.getmodule(function) is module
    assert inspect.getsourcefile(function) == module.__file__


@pytest.mark.parametrize("path", [CANONICAL, LEGACY])
@pytest.mark.parametrize("attribute", [*EXPORTS, "normalize_service", "normalizar_servicio"])
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
def test_quote_wrapper_and_normalizer_use_shared_globals(path, monkeypatch):
    module = importlib.import_module(path)
    peer = importlib.import_module(LEGACY if path == CANONICAL else CANONICAL)
    replacement = MagicMock()
    replacement.invoke.return_value = "Controlled service response"
    with monkeypatch.context() as patch:
        patch.setattr(module, "generar_cotizacion", replacement)
        assert peer.identify_quote_service.invoke({"service": "reparacion"}) == "Controlled service response"
        replacement.invoke.assert_called_once_with({"servicio": "reparacion"})
    normalizer = MagicMock(return_value="diagnostico")
    with monkeypatch.context() as patch:
        patch.setattr(module, "normalize_service", normalizer)
        assert peer.generar_cotizacion.invoke({"servicio": "fixture"}).startswith("Servicio: diagnostico.")
        normalizer.assert_called_once_with("fixture")


@pytest.mark.parametrize("name,key", [("generar_cotizacion", "servicio"), ("identify_quote_service", "service")])
def test_identification_preserves_results_and_validation(name, key):
    tool = getattr(importlib.import_module(CANONICAL), name)
    assert tool.invoke({key: " REPARACIÓN "}) == (
        "Servicio: reparacion. Tarifa de mano de obra pendiente de validacion. No se puede confirmar un precio total.")
    assert tool.invoke({key: "otro"}) == (
        "No se encontro una cotizacion para el servicio solicitado. Se requiere evaluacion comercial.")
    for args in ({}, {key: None}, {key: 3}):
        with pytest.raises(ValidationError):
            tool.invoke(args)


def test_registries_wrappers_and_captured_references(network, monkeypatch):
    graph_module, _ = network
    module = importlib.import_module(CANONICAL)
    agent = importlib.import_module("app.agents.decentralized.sales")
    requests = importlib.import_module("app.agents.decentralized.tools.inventory_request_tools")
    handoffs = importlib.import_module("app.agents.decentralized.tools.sales_handoff_tools")
    assert agent.sales_tools is agent.ventas_tools is graph_module.sales_tools
    assert [tool.name for tool in agent.sales_tools] == ["transfer_to_billing", "request_inventory",
        "transfer_to_support", "identify_quote_service", "transfer_to_hardware", "consultar_base_conocimiento"]
    assert agent.sales_tools[3] is agent.identify_quote_service is module.identify_quote_service
    assert agent.generar_cotizacion is module.generar_cotizacion
    assert requests._request is requests.legacy_inventory_request_tools[0] is module.solicitar_inventario
    assert handoffs._hardware is module.transferir_a_tecnico
    assert requests.request_inventory.invoke({"query": "dos SSD"}) == module.solicitar_inventario.invoke({"consulta": "dos SSD"}) == {
        "accion": "CONSULTAR_DISPONIBILIDAD", "consulta": "dos SSD"}
    registered = graph_module.build_graph().get_graph().nodes["ventas_tools"].data.tools_by_name
    assert all(registered[name] is getattr(module, name) for name in EXPORTS)
    captured = agent.identify_quote_service
    with monkeypatch.context() as patch:
        patch.setattr(module, "identify_quote_service", MagicMock())
        assert agent.identify_quote_service is registered["identify_quote_service"] is captured
    assert module.identify_quote_service is captured


@pytest.mark.parametrize("names", [["identify_quote_service"], ["generar_cotizacion"], ["identify_quote_service", "generar_cotizacion"]])
def test_checkpoint_batch_and_handoff_keep_ids_and_service_context(network, monkeypatch, names):
    graph_module, controls = network
    calls = [dict(name=name, args={"service" if name == "identify_quote_service" else "servicio": "diagnostico"},
                  id="quote-" + str(index)) for index, name in enumerate(names)]
    saver = MemorySaver()
    config = {"configurable": {"thread_id": "sales-tools-module"}}
    graph_module.build_graph(checkpointer=saver).update_state(config, dict(
        messages=[HumanMessage(content="Consulta general"), AIMessage(content="", tool_calls=calls)],
        current_agent="ventas", handoff_count=0, handoff_history=[], handoff_records=[]), as_node="ventas")
    first = graph_module.build_graph(checkpointer=saver).invoke(None, config, interrupt_after=["auditar_ventas"])
    outputs = [message for message in first["messages"] if isinstance(message, ToolMessage)]
    assert [(message.name, message.tool_call_id) for message in outputs] == [(call["name"], call["id"]) for call in calls]
    assert all(message.status != "error" and "Tarifa de mano de obra pendiente" in message.content for message in outputs)
    agent = importlib.import_module("app.agents.decentralized.sales")
    model = MagicMock()
    model.invoke.return_value = AIMessage(content="", tool_calls=[dict(name="transfer_to_hardware", args={"reason": "Evaluar"}, id="handoff")])
    monkeypatch.setattr(agent, "sales_llm", model)
    result = graph_module.build_graph(checkpointer=saver).invoke(None, config, interrupt_after=["auditar_ventas"])
    outputs = [message for message in result["messages"] if isinstance(message, ToolMessage)]
    assert [(message.name, message.tool_call_id) for message in outputs] == [(call["name"], call["id"]) for call in calls] + [("transfer_to_hardware", "handoff")]
    assert result["handoff_history"] == [{"origin": "ventas", "destination": "tecnico"}]
    assert result["handoff_count"] == 1
    assert controls["inventory_calls"] == controls["rag_calls"] == []
    assert not result.get("quote_id") and not result.get("payment_id")


def test_legacy_shim_and_single_canonical_ast():
    legacy = (ROOT / "app/agents/decentralized/tools/ventas_tools.py").read_text(encoding="utf-8")
    assert '".sales_tools"' in legacy
    assert not any(isinstance(node, (ast.FunctionDef, ast.ClassDef)) for node in ast.parse(legacy).body)
    tree = ast.parse((ROOT / "app/agents/decentralized/tools/sales_tools.py").read_text(encoding="utf-8"))
    assert {node.name for node in tree.body if isinstance(node, ast.FunctionDef)} == {
        "solicitar_inventario", "normalize_service", "generar_cotizacion", "identify_quote_service", "transferir_a_tecnico"}


ORIGINAL_CONTRACTS = {'solicitar_inventario': {'description': 'Deriva a Almacén una consulta comercial de disponibilidad, sin '
                                         'inventar repuestos.',
                          'schema': {'description': 'Deriva a Almacén una consulta comercial de '
                                                    'disponibilidad, sin inventar repuestos.',
                                     'properties': {'consulta': {'title': 'Consulta', 'type': 'string'}},
                                     'required': ['consulta'],
                                     'title': 'solicitar_inventario',
                                     'type': 'object'},
                          'call_schema': {'description': 'Deriva a Almacén una consulta comercial de '
                                                         'disponibilidad, sin inventar repuestos.',
                                          'properties': {'consulta': {'title': 'Consulta', 'type': 'string'}},
                                          'required': ['consulta'],
                                          'title': 'solicitar_inventario',
                                          'type': 'object'}},
 'generar_cotizacion': {'description': 'Identifica el servicio solicitado sin inventar tarifas.\n'
                                       '\n'
                                       'Los precios de repuestos deben provenir de PostgreSQL.\n'
                                       'La mano de obra requiere una tarifa verificada.',
                        'schema': {'description': 'Identifica el servicio solicitado sin inventar tarifas.\n'
                                                  '\n'
                                                  'Los precios de repuestos deben provenir de PostgreSQL.\n'
                                                  'La mano de obra requiere una tarifa verificada.',
                                   'properties': {'servicio': {'title': 'Servicio', 'type': 'string'}},
                                   'required': ['servicio'],
                                   'title': 'generar_cotizacion',
                                   'type': 'object'},
                        'call_schema': {'description': 'Identifica el servicio solicitado sin inventar '
                                                       'tarifas.\n'
                                                       '\n'
                                                       'Los precios de repuestos deben provenir de '
                                                       'PostgreSQL.\n'
                                                       'La mano de obra requiere una tarifa verificada.',
                                        'properties': {'servicio': {'title': 'Servicio', 'type': 'string'}},
                                        'required': ['servicio'],
                                        'title': 'generar_cotizacion',
                                        'type': 'object'}},
 'identify_quote_service': {'description': 'Identifica el servicio solicitado sin inventar tarifas.\n'
                                           '\n'
                                           'Los precios de repuestos deben provenir de PostgreSQL.\n'
                                           'La mano de obra requiere una tarifa verificada.',
                            'schema': {'properties': {'service': {'title': 'Service', 'type': 'string'}},
                                       'required': ['service'],
                                       'title': 'identify_quote_service',
                                       'type': 'object'},
                            'call_schema': {'description': 'Identifica el servicio solicitado sin inventar '
                                                           'tarifas.\n'
                                                           '\n'
                                                           'Los precios de repuestos deben provenir de '
                                                           'PostgreSQL.\n'
                                                           'La mano de obra requiere una tarifa verificada.',
                                            'properties': {'service': {'title': 'Service', 'type': 'string'}},
                                            'required': ['service'],
                                            'title': 'identify_quote_service',
                                            'type': 'object'}},
 'transferir_a_tecnico': {'description': 'Transfiere una solicitud al agente Tecnico cuando\n'
                                         'requiere diagnostico especializado.',
                          'schema': {'description': 'Transfiere una solicitud al agente Tecnico cuando\n'
                                                    'requiere diagnostico especializado.',
                                     'properties': {'motivo': {'title': 'Motivo', 'type': 'string'}},
                                     'required': ['motivo'],
                                     'title': 'transferir_a_tecnico',
                                     'type': 'object'},
                          'call_schema': {'description': 'Transfiere una solicitud al agente Tecnico cuando\n'
                                                         'requiere diagnostico especializado.',
                                          'properties': {'motivo': {'title': 'Motivo', 'type': 'string'}},
                                          'required': ['motivo'],
                                          'title': 'transferir_a_tecnico',
                                          'type': 'object'}}}
