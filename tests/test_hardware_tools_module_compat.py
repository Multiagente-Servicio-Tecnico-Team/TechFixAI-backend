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
CANONICAL = "app.agents.decentralized.tools.hardware_tools"
LEGACY = "app.agents.decentralized.tools.tecnico_tools"
EXPORTS = ["diagnosticar_problema", "diagnose_issue", "transferir_a_ventas", "transferir_a_almacen"]


@pytest.mark.parametrize("first", ["hardware_tools", "tecnico_tools"])
@pytest.mark.parametrize("style", ["importlib", "package"])
def test_fresh_import_orders_share_module_and_execute_once(first, style):
    script = r'''
import importlib, json, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
executions = []
def profile(frame, event, arg):
    if event == "call" and frame.f_code.co_name == "<module>" and Path(frame.f_code.co_filename).name == "hardware_tools.py":
        executions.append(frame.f_code.co_filename)
sys.setprofile(profile)
def load(name):
    if sys.argv[3] == "package":
        namespace = {}
        exec("from app.agents.decentralized.tools import " + name, namespace)
        return namespace[name]
    return importlib.import_module("app.agents.decentralized.tools." + name)
one = load(sys.argv[2])
two = load("tecnico_tools" if sys.argv[2] == "hardware_tools" else "hardware_tools")
from app.agents.decentralized.tools import hardware_tools, tecnico_tools
assert one is two is hardware_tools is tecnico_tools
assert load("hardware_tools") is load("tecnico_tools") is one
assert sys.modules["app.agents.decentralized.tools.hardware_tools"] is sys.modules["app.agents.decentralized.tools.tecnico_tools"] is one
assert one.__name__ == one.__spec__.name == "app.agents.decentralized.tools.hardware_tools"
assert Path(one.__file__).name == "hardware_tools.py"
assert len(executions) == 1
assert not any(name.startswith(("app.database", "app.rag", "langchain_groq", "psycopg")) for name in sys.modules)
sys.setprofile(None)
print(json.dumps({"executions": len(executions)}))
'''
    result = subprocess.run([sys.executable, "-B", "-c", script, str(ROOT), first, style],
                            cwd=ROOT, capture_output=True, text=True, timeout=60, check=True)
    assert json.loads(result.stdout) == {"executions": 1}


@pytest.mark.parametrize("name", EXPORTS)
def test_decorated_identity_metadata_inspection_and_frozen_contract(name):
    canonical, legacy = importlib.import_module(CANONICAL), importlib.import_module(LEGACY)
    assert canonical is legacy
    assert canonical.__name__ == canonical.__spec__.name == CANONICAL
    assert Path(canonical.__file__) == ROOT / "app/agents/decentralized/tools/hardware_tools.py"
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
@pytest.mark.parametrize("attribute", EXPORTS)
def test_bidirectional_export_monkeypatch_and_restoration(path, attribute, monkeypatch):
    module = importlib.import_module(path)
    peer = importlib.import_module(LEGACY if path == CANONICAL else CANONICAL)
    original = getattr(module, attribute)
    with monkeypatch.context() as patch:
        replacement = MagicMock()
        patch.setattr(module, attribute, replacement)
        assert getattr(peer, attribute) is replacement
    assert getattr(module, attribute) is getattr(peer, attribute) is original


@pytest.mark.parametrize("path", [CANONICAL, LEGACY])
def test_diagnostic_wrapper_resolves_shared_global_dynamically(path, monkeypatch):
    module = importlib.import_module(path)
    peer = importlib.import_module(LEGACY if path == CANONICAL else CANONICAL)
    original = module.diagnosticar_problema
    replacement = MagicMock()
    replacement.func.return_value = "Controlled preliminary diagnosis"
    with monkeypatch.context() as patch:
        patch.setattr(module, "diagnosticar_problema", replacement)
        assert peer.diagnose_issue.invoke({"symptom": "no enciende"}) == "Controlled preliminary diagnosis"
        replacement.func.assert_called_once_with(sintoma="no enciende")
    assert module.diagnosticar_problema is peer.diagnosticar_problema is original


@pytest.mark.parametrize("name,key", [("diagnose_issue", "symptom"), ("diagnosticar_problema", "sintoma")])
def test_preliminary_diagnosis_results_and_validation(name, key):
    tool = getattr(importlib.import_module(CANONICAL), name)
    assert tool.invoke({key: "  NO ENCIENDE  "}) == (
        "Posible falla en la fuente de alimentación. Se recomienda revisar la fuente y el cable de energía.")
    assert tool.invoke({key: "desconocido"}) == (
        "No se encontró un diagnóstico preliminar para el síntoma indicado. Se requiere una revisión técnica más detallada.")
    for args in ({}, {key: None}, {key: 3}):
        with pytest.raises(ValidationError):
            tool.invoke(args)


@pytest.mark.parametrize("path", [CANONICAL, LEGACY])
def test_local_handoff_results_and_distinct_error_contracts(path):
    module = importlib.import_module(path)
    assert module.transferir_a_ventas.invoke(dict(motivo="Evaluar", alcance="repuestos", nombre_repuesto=" SSD ", cantidad=2)) == {
        "accion": "SOLICITAR_COTIZACION", "motivo": "Evaluar", "alcance": "repuestos", "nombre_repuesto": "SSD", "cantidad": 2}
    assert module.transferir_a_almacen.invoke(dict(motivo="Evaluar", nombre_repuesto=" SSD ", cantidad=2)) == {
        "accion": "TRANSFERIR_ALMACEN", "motivo": "Evaluar", "nombre_repuesto": "SSD", "cantidad": 2}
    assert module.transferir_a_almacen.invoke(dict(motivo="Evaluar", nombre_repuesto=" ")) == {
        "error": "El nombre del repuesto es obligatorio."}
    for quantity in (0, -1):
        with pytest.raises(ValueError, match="La cantidad debe ser un entero positivo"):
            module.transferir_a_ventas.invoke(dict(motivo="Evaluar", alcance="repuestos", cantidad=quantity))
        assert module.transferir_a_almacen.invoke(dict(motivo="Evaluar", nombre_repuesto="SSD", cantidad=quantity)) == {
            "error": "La cantidad debe ser un entero positivo."}
    with pytest.raises(ValidationError):
        module.transferir_a_ventas.invoke(dict(motivo="Evaluar", alcance="invalid"))


def test_agent_graph_and_wrappers_keep_captured_references(network, monkeypatch):
    graph_module, _ = network
    tools = importlib.import_module(CANONICAL)
    agent = importlib.import_module("app.agents.decentralized.hardware")
    wrappers = importlib.import_module("app.agents.decentralized.tools.hardware_handoff_tools")
    software = importlib.import_module("app.agents.decentralized.tools.software_tools")
    assert agent.hardware_tools is agent.tecnico_tools is graph_module.hardware_tools
    assert [tool.name for tool in agent.hardware_tools] == ["transfer_to_logistics", "transfer_to_support",
        "transfer_to_software", "diagnose_issue", "transfer_to_sales", "transfer_to_warehouse", "consultar_base_conocimiento"]
    assert agent.hardware_tools[3] is agent.diagnose_issue is tools.diagnose_issue
    assert wrappers._sales is software._sales is tools.transferir_a_ventas
    assert wrappers._warehouse is tools.transferir_a_almacen
    registered = graph_module.build_graph().get_graph().nodes["tecnico_tools"].data.tools_by_name
    assert registered["diagnose_issue"] is tools.diagnose_issue
    assert registered["diagnosticar_problema"] is graph_module.diagnosticar_problema is tools.diagnosticar_problema
    captured = agent.diagnose_issue
    with monkeypatch.context() as patch:
        patch.setattr(tools, "diagnose_issue", MagicMock())
        assert agent.diagnose_issue is agent.hardware_tools[3] is registered["diagnose_issue"] is captured
    assert tools.diagnose_issue is captured


@pytest.mark.parametrize("style", ["english", "legacy", "mixed"])
def test_checkpoint_diagnostic_batch_then_handoff_preserves_ids(network, monkeypatch, style):
    graph_module, controls = network
    tools = importlib.import_module(CANONICAL)
    variants = [("diagnose_issue", "symptom"), ("diagnosticar_problema", "sintoma")]
    selected = variants if style == "mixed" else [variants[style == "legacy"]]
    calls = [dict(name=name, args={key: "no enciende"}, id="diagnostic-" + str(index))
             for index, (name, key) in enumerate(selected)]
    config = {"configurable": {"thread_id": "hardware-tools-module"}}
    saver = MemorySaver()
    graph_module.build_graph(checkpointer=saver).update_state(config, dict(
        messages=[HumanMessage(content="Consulta general"), AIMessage(content="", tool_calls=calls)],
        current_agent="tecnico", handoff_count=0, handoff_history=[], handoff_records=[]), as_node="tecnico")
    first = graph_module.build_graph(checkpointer=saver).invoke(None, config, interrupt_after=["auditar_tecnico"])
    outputs = [message for message in first["messages"] if isinstance(message, ToolMessage)]
    assert [(message.name, message.tool_call_id) for message in outputs] == [(call["name"], call["id"]) for call in calls]
    assert all(message.content == tools.diagnose_issue.invoke({"symptom": "no enciende"}) for message in outputs)
    assert all(message.status != "error" for message in outputs)
    agent = importlib.import_module("app.agents.decentralized.hardware")
    model = MagicMock()
    model.invoke.return_value = AIMessage(content="", tool_calls=[dict(name="transfer_to_software", args={"reason": "Evaluar"}, id="handoff")])
    monkeypatch.setattr(agent, "hardware_llm", model)
    result = graph_module.build_graph(checkpointer=saver).invoke(None, config, interrupt_after=["auditar_tecnico"])
    outputs = [message for message in result["messages"] if isinstance(message, ToolMessage)]
    assert [(message.name, message.tool_call_id) for message in outputs] == [(call["name"], call["id"]) for call in calls] + [("transfer_to_software", "handoff")]
    assert result["handoff_history"] == [{"origin": "tecnico", "destination": "software"}]
    assert result["handoff_count"] == 1
    assert controls["rag_calls"] == controls["inventory_calls"] == []
    assert not result.get("diagnosis_id") and not result.get("quote_id") and not result.get("payment_id")


def test_legacy_shim_and_canonical_ast_have_single_implementation():
    legacy = (ROOT / "app/agents/decentralized/tools/tecnico_tools.py").read_text(encoding="utf-8")
    assert '".hardware_tools"' in legacy
    assert not any(isinstance(node, (ast.FunctionDef, ast.ClassDef)) for node in ast.parse(legacy).body)
    tree = ast.parse((ROOT / "app/agents/decentralized/tools/hardware_tools.py").read_text(encoding="utf-8"))
    assert {node.name for node in tree.body if isinstance(node, ast.FunctionDef)} == {
        "diagnosticar_problema", "_diagnose_issue", "transferir_a_ventas", "transferir_a_almacen"}


ORIGINAL_CONTRACTS = {'diagnosticar_problema': {'description': 'Realiza un diagnóstico preliminar a partir del síntoma\n'
                                          'reportado por el usuario.',
                           'schema': {'description': 'Realiza un diagnóstico preliminar a partir del '
                                                     'síntoma\n'
                                                     'reportado por el usuario.',
                                      'properties': {'sintoma': {'title': 'Sintoma', 'type': 'string'}},
                                      'required': ['sintoma'],
                                      'title': 'diagnosticar_problema',
                                      'type': 'object'},
                           'call_schema': {'description': 'Realiza un diagnóstico preliminar a partir del '
                                                          'síntoma\n'
                                                          'reportado por el usuario.',
                                           'properties': {'sintoma': {'title': 'Sintoma', 'type': 'string'}},
                                           'required': ['sintoma'],
                                           'title': 'diagnosticar_problema',
                                           'type': 'object'}},
 'diagnose_issue': {'description': 'Realiza un diagnóstico preliminar a partir del síntoma\n'
                                   'reportado por el usuario.',
                    'schema': {'properties': {'symptom': {'title': 'Symptom', 'type': 'string'}},
                               'required': ['symptom'],
                               'title': 'diagnose_issue',
                               'type': 'object'},
                    'call_schema': {'description': 'Realiza un diagnóstico preliminar a partir del síntoma\n'
                                                   'reportado por el usuario.',
                                    'properties': {'symptom': {'title': 'Symptom', 'type': 'string'}},
                                    'required': ['symptom'],
                                    'title': 'diagnose_issue',
                                    'type': 'object'}},
 'transferir_a_ventas': {'description': 'Solicita cotización declarando su alcance para validar la ruta.\n'
                                        '\n'
                                        'solo_servicio: únicamente revisión, diagnóstico o mano de obra sin '
                                        'repuestos.\n'
                                        'repuestos: reemplazo o reparación con componentes; requiere Almacén '
                                        'primero.\n'
                                        'sin_determinar: falta definir qué se cotiza. No equivale a '
                                        'solo_servicio.\n'
                                        'Si no conoces el repuesto exacto, deja nombre_repuesto vacío; no lo '
                                        'inventes.',
                         'schema': {'description': 'Solicita cotización declarando su alcance para validar '
                                                   'la ruta.\n'
                                                   '\n'
                                                   'solo_servicio: únicamente revisión, diagnóstico o mano '
                                                   'de obra sin repuestos.\n'
                                                   'repuestos: reemplazo o reparación con componentes; '
                                                   'requiere Almacén primero.\n'
                                                   'sin_determinar: falta definir qué se cotiza. No equivale '
                                                   'a solo_servicio.\n'
                                                   'Si no conoces el repuesto exacto, deja nombre_repuesto '
                                                   'vacío; no lo inventes.',
                                    'properties': {'motivo': {'title': 'Motivo', 'type': 'string'},
                                                   'alcance': {'enum': ['solo_servicio',
                                                                        'repuestos',
                                                                        'sin_determinar'],
                                                               'title': 'Alcance',
                                                               'type': 'string'},
                                                   'nombre_repuesto': {'default': '',
                                                                       'title': 'Nombre Repuesto',
                                                                       'type': 'string'},
                                                   'cantidad': {'default': 1,
                                                                'title': 'Cantidad',
                                                                'type': 'integer'}},
                                    'required': ['motivo', 'alcance'],
                                    'title': 'transferir_a_ventas',
                                    'type': 'object'},
                         'call_schema': {'description': 'Solicita cotización declarando su alcance para '
                                                        'validar la ruta.\n'
                                                        '\n'
                                                        'solo_servicio: únicamente revisión, diagnóstico o '
                                                        'mano de obra sin repuestos.\n'
                                                        'repuestos: reemplazo o reparación con componentes; '
                                                        'requiere Almacén primero.\n'
                                                        'sin_determinar: falta definir qué se cotiza. No '
                                                        'equivale a solo_servicio.\n'
                                                        'Si no conoces el repuesto exacto, deja '
                                                        'nombre_repuesto vacío; no lo inventes.',
                                         'properties': {'motivo': {'title': 'Motivo', 'type': 'string'},
                                                        'alcance': {'enum': ['solo_servicio',
                                                                             'repuestos',
                                                                             'sin_determinar'],
                                                                    'title': 'Alcance',
                                                                    'type': 'string'},
                                                        'nombre_repuesto': {'default': '',
                                                                            'title': 'Nombre Repuesto',
                                                                            'type': 'string'},
                                                        'cantidad': {'default': 1,
                                                                     'title': 'Cantidad',
                                                                     'type': 'integer'}},
                                         'required': ['motivo', 'alcance'],
                                         'title': 'transferir_a_ventas',
                                         'type': 'object'}},
 'transferir_a_almacen': {'description': 'Solicita verificar un repuesto identificado\n'
                                         'para una reparación.\n'
                                         '\n'
                                         'nombre_repuesto: nombre exacto del repuesto.\n'
                                         'cantidad: unidades requeridas.',
                          'schema': {'description': 'Solicita verificar un repuesto identificado\n'
                                                    'para una reparación.\n'
                                                    '\n'
                                                    'nombre_repuesto: nombre exacto del repuesto.\n'
                                                    'cantidad: unidades requeridas.',
                                     'properties': {'motivo': {'title': 'Motivo', 'type': 'string'},
                                                    'nombre_repuesto': {'title': 'Nombre Repuesto',
                                                                        'type': 'string'},
                                                    'cantidad': {'default': 1,
                                                                 'title': 'Cantidad',
                                                                 'type': 'integer'}},
                                     'required': ['motivo', 'nombre_repuesto'],
                                     'title': 'transferir_a_almacen',
                                     'type': 'object'},
                          'call_schema': {'description': 'Solicita verificar un repuesto identificado\n'
                                                         'para una reparación.\n'
                                                         '\n'
                                                         'nombre_repuesto: nombre exacto del repuesto.\n'
                                                         'cantidad: unidades requeridas.',
                                          'properties': {'motivo': {'title': 'Motivo', 'type': 'string'},
                                                         'nombre_repuesto': {'title': 'Nombre Repuesto',
                                                                             'type': 'string'},
                                                         'cantidad': {'default': 1,
                                                                      'title': 'Cantidad',
                                                                      'type': 'integer'}},
                                          'required': ['motivo', 'nombre_repuesto'],
                                          'title': 'transferir_a_almacen',
                                          'type': 'object'}}}
