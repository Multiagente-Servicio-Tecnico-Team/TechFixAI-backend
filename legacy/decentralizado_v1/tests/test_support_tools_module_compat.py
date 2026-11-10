import ast
from copy import deepcopy
import importlib
import inspect
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver

import app.agents.decentralized.tools as tools_package
from test_software_e2e import network


ROOT = Path(__file__).resolve().parents[1]
PREFIX = tools_package.__name__ + "."
CANONICAL = PREFIX + "support_tools"
LEGACY = PREFIX + "soporte_tools"
EXPORTS = ["transferir_a_software", "transferir_a_soporte", "consultar_estado_ticket",
           "get_ticket_status", "transferir_a_tecnico", "transferir_a_ventas"]
FACTORIES = ["authenticated_ticket_tool", "authenticated_ticket_status_tool"]
VARIANTS = [("authenticated_ticket_tool", "consultar_estado_ticket", "numero_ticket"),
            ("authenticated_ticket_status_tool", "get_ticket_status", "ticket_id")]


@pytest.mark.parametrize("first", ["support_tools", "soporte_tools"])
@pytest.mark.parametrize("style", ["importlib", "package"])
def test_fresh_import_orders_share_identity_without_extra_initialization(first, style):
    script = r'''
import importlib, json, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
executions = []
def profile(frame, event, arg):
    if event == "call" and frame.f_code.co_name == "<module>" and Path(frame.f_code.co_filename).name == "support_tools.py":
        executions.append(frame.f_code.co_filename)
sys.setprofile(profile)
def load(name):
    if sys.argv[3] == "package":
        namespace = {}
        exec("from app.agents.decentralized.tools import " + name, namespace)
        return namespace[name]
    return importlib.import_module("app.agents.decentralized.tools." + name)
one = load(sys.argv[2])
two = load("soporte_tools" if sys.argv[2] == "support_tools" else "support_tools")
from app.agents.decentralized.tools import support_tools, soporte_tools
assert one is two is support_tools is soporte_tools
assert load("support_tools") is load("soporte_tools") is one
assert one.__name__ == one.__spec__.name == "app.agents.decentralized.tools.support_tools"
assert Path(one.__file__).name == "support_tools.py"
assert len(executions) == 1
assert not any(name.startswith(("app.database", "app.rag", "langchain_groq", "psycopg")) for name in sys.modules)
sys.setprofile(None)
print(json.dumps({"executions": len(executions)}))
'''
    result = subprocess.run([sys.executable, "-B", "-c", script, str(ROOT), first, style],
                            cwd=ROOT, capture_output=True, text=True, timeout=60, check=True)
    assert json.loads(result.stdout) == {"executions": 1}


@pytest.mark.parametrize("name", EXPORTS)
def test_decorated_identity_metadata_and_frozen_simulated_contract(name):
    canonical, legacy = importlib.import_module(CANONICAL), importlib.import_module(LEGACY)
    assert canonical is legacy
    assert canonical.__name__ == canonical.__spec__.name == CANONICAL
    assert Path(canonical.__file__) == ROOT / "app/agents/decentralized/tools/support_tools.py"
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


@pytest.mark.parametrize("factory,name,parameter", VARIANTS)
def test_factory_aliases_runtime_injection_and_frozen_public_contract(factory, name, parameter):
    canonical, legacy = importlib.import_module(CANONICAL), importlib.import_module(LEGACY)
    function = getattr(canonical, factory)
    assert function is getattr(legacy, factory)
    assert function.__module__ == CANONICAL
    assert inspect.getmodule(function) is canonical
    assert str(inspect.signature(function)) == "(repository)"
    tool = function(MagicMock())
    assert tool.name == name and tool.func.__module__ == CANONICAL
    assert inspect.getmodule(tool.func) is canonical
    assert inspect.getsourcefile(tool.func) == canonical.__file__
    assert list(inspect.signature(tool.func).parameters) == [parameter, "runtime"]
    assert set(tool.args_schema.model_fields) == {parameter, "runtime"}
    assert tool.description == ORIGINAL_CONTRACTS[factory]["description"]
    assert tool.tool_call_schema.model_json_schema() == ORIGINAL_CONTRACTS[factory]["call_schema"]
    assert set(tool.tool_call_schema.model_json_schema()["properties"]) == {parameter}


@pytest.mark.parametrize("path", [CANONICAL, LEGACY])
@pytest.mark.parametrize("attribute", EXPORTS + FACTORIES)
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
def test_simulated_wrapper_uses_shared_global_and_restores(path, monkeypatch):
    module = importlib.import_module(path)
    peer = importlib.import_module(LEGACY if path == CANONICAL else CANONICAL)
    original = module.consultar_estado_ticket
    replacement = MagicMock()
    replacement.func.return_value = "Controlled simulated lookup"
    with monkeypatch.context() as patch:
        patch.setattr(module, "consultar_estado_ticket", replacement)
        assert peer.get_ticket_status.invoke({"ticket_id": 1001}) == "Controlled simulated lookup"
        replacement.func.assert_called_once_with(numero_ticket=1001)
    assert module.consultar_estado_ticket is original


@pytest.mark.parametrize("path", [CANONICAL, LEGACY])
@pytest.mark.parametrize("factory,name,parameter", VARIANTS)
def test_direct_factory_uses_runtime_context_and_hides_repository_errors(path, factory, name, parameter):
    module = importlib.import_module(path)
    repo = MagicMock()
    repo.get_ticket.return_value = dict(id=1001, code="TCK-SYNTHETIC", status="NEW")
    tool = getattr(module, factory)(repo)
    args = {parameter: 1001}
    result = tool.func(**args, runtime=SimpleNamespace(context={"authenticated_customer_id": 11}))
    assert result == dict(verified=True, ticket_id=1001, ticket_code="TCK-SYNTHETIC", status="NEW")
    repo.get_ticket.assert_called_once_with(customer_id=11, ticket_id=1001)
    repo.reset_mock()
    for context in (None, {}, {"authenticated_customer_id": True}, {"authenticated_customer_id": "11"}):
        assert tool.func(**args, runtime=SimpleNamespace(context=context)) == {
            "verified": False, "detail": "Se requiere una sesión autenticada."}
    repo.get_ticket.assert_not_called()
    for error in (LookupError("foreign-private"), LookupError("missing-private"), RuntimeError("storage-private")):
        repo.get_ticket.side_effect = error
        result = tool.func(**args, runtime=SimpleNamespace(context={"authenticated_customer_id": 12}))
        assert result["verified"] is False and set(result) == {"verified", "detail"}
        assert "private" not in json.dumps(result)
    assert len(repo.mock_calls) == 3


def test_consumer_references_and_authenticated_registry_keep_semantics(network, monkeypatch):
    graph_module, _ = network
    module = importlib.import_module(CANONICAL)
    agent = importlib.import_module("app.agents.decentralized.support")
    assert agent.support_tools is agent.soporte_tools is graph_module.support_tools
    assert [tool.name for tool in agent.support_tools] == ["transfer_to_warranty", "transfer_to_logistics",
        "transfer_to_billing", "get_ticket_status", "transfer_to_hardware", "transfer_to_sales",
        "transfer_to_software", "consultar_base_conocimiento"]
    assert agent.get_ticket_status is module.get_ticket_status
    software = importlib.import_module(PREFIX + "software_tools")
    billing = importlib.import_module(PREFIX + "billing_tools")
    purchasing = importlib.import_module(PREFIX + "purchasing_tools")
    assert software._support is module.transferir_a_soporte
    assert software._hardware is module.transferir_a_tecnico
    assert billing._sales is purchasing._sales is module.transferir_a_ventas
    wrappers = importlib.import_module(PREFIX + "support_handoff_tools")
    assert wrappers._hardware is module.transferir_a_tecnico
    assert wrappers._software is module.transferir_a_software
    assert wrappers._sales is module.transferir_a_ventas
    registered = graph_module.build_graph(checkpointer=MemorySaver(), financial_repository=MagicMock()).get_graph().nodes["soporte_tools"].data.tools_by_name
    for name in ("get_ticket_status", "consultar_estado_ticket"):
        assert "runtime" in registered[name].args_schema.model_fields
        assert registered[name] is not getattr(module, name)
    captured = agent.get_ticket_status
    with monkeypatch.context() as patch:
        patch.setattr(module, "get_ticket_status", MagicMock())
        assert agent.get_ticket_status is captured
    assert module.get_ticket_status is captured


@pytest.mark.parametrize("ticket_id,expected", [(1001, "El ticket 1001 se encuentra: En revisión"),
    (9999, "No se encontró el ticket 9999")])
def test_simulated_results_remain_distinct_from_authenticated(ticket_id, expected):
    module = importlib.import_module(CANONICAL)
    assert module.get_ticket_status.invoke({"ticket_id": ticket_id}) == expected
    assert module.consultar_estado_ticket.invoke({"numero_ticket": ticket_id}) == expected


@pytest.mark.parametrize("path", [CANONICAL, LEGACY])
@pytest.mark.parametrize("name,parameter", [("get_ticket_status", "ticket_id"), ("consultar_estado_ticket", "numero_ticket")])
def test_authenticated_checkpoint_reauthorizes_injected_context_without_simulation(network, path, name, parameter, monkeypatch):
    graph_module, _ = network
    module = importlib.import_module(path)
    simulated = MagicMock(side_effect=AssertionError("Simulated fallback forbidden"))
    monkeypatch.setattr(module, "consultar_estado_ticket", simulated)
    repo = MagicMock()
    def lookup(*, customer_id, ticket_id):
        if customer_id != 11:
            raise LookupError("private owner")
        assert ticket_id == 1001
        return dict(id=1001, code="TCK-SYNTHETIC", status="NEW")
    repo.get_ticket.side_effect = lookup
    request = AIMessage(content="", id="request", tool_calls=[dict(name=name, args={parameter: 1001,
        "authenticated_customer_id": 11, "runtime": {"context": {"authenticated_customer_id": 11}}}, id="lookup")])
    before = deepcopy(request)
    saver = MemorySaver()
    for customer in (11, 12):
        config = {"configurable": {"thread_id": "support-tools-module-" + str(customer)}}
        graph_module.build_graph(checkpointer=saver, financial_repository=repo).update_state(config, dict(
            messages=[HumanMessage(content="Estado del ticket"), request], customer_id=11,
            current_agent="soporte", handoff_count=0, handoff_history=[]), as_node="soporte")
        result = graph_module.build_graph(checkpointer=saver, financial_repository=repo).invoke(None, config,
            context={"authenticated_customer_id": customer}, interrupt_after=["auditar_soporte"])
        outputs = [message for message in result["messages"] if isinstance(message, ToolMessage)]
        assert len(outputs) == 1 and (outputs[0].name, outputs[0].tool_call_id) == (name, "lookup")
        data = json.loads(outputs[0].content)
        assert data["verified"] is (customer == 11)
        if customer == 12:
            assert set(data) == {"verified", "detail"} and "private" not in outputs[0].content
        assert result["handoff_history"] == [] and result["handoff_count"] == 0
    assert request == before
    assert [call.kwargs for call in repo.get_ticket.call_args_list] == [
        dict(customer_id=11, ticket_id=1001), dict(customer_id=12, ticket_id=1001)]
    assert len(repo.mock_calls) == 2
    simulated.assert_not_called()


def test_legacy_shim_and_single_canonical_ast():
    legacy = (ROOT / "app/agents/decentralized/tools/soporte_tools.py").read_text(encoding="utf-8")
    assert '".support_tools"' in legacy
    assert not any(isinstance(node, (ast.FunctionDef, ast.ClassDef)) for node in ast.parse(legacy).body)
    tree = ast.parse((ROOT / "app/agents/decentralized/tools/support_tools.py").read_text(encoding="utf-8"))
    assert {node.name for node in tree.body if isinstance(node, ast.FunctionDef)} == {
        "authenticated_ticket_tool", "authenticated_ticket_status_tool", "transferir_a_software", "transferir_a_soporte",
        "consultar_estado_ticket", "_get_ticket_status", "transferir_a_tecnico", "transferir_a_ventas"}


ORIGINAL_CONTRACTS = {'transferir_a_software': {'description': 'Deriva una consulta lógica a Software sin ejecutar cambios ni '
                                          'diagnosticar.',
                           'schema': {'description': 'Deriva una consulta lógica a Software sin ejecutar '
                                                     'cambios ni diagnosticar.',
                                      'properties': {'motivo': {'title': 'Motivo', 'type': 'string'}},
                                      'required': ['motivo'],
                                      'title': 'transferir_a_software',
                                      'type': 'object'},
                           'call_schema': {'description': 'Deriva una consulta lógica a Software sin '
                                                          'ejecutar cambios ni diagnosticar.',
                                           'properties': {'motivo': {'title': 'Motivo', 'type': 'string'}},
                                           'required': ['motivo'],
                                           'title': 'transferir_a_software',
                                           'type': 'object'}},
 'transferir_a_soporte': {'description': 'Devuelve a Soporte una consulta de ticket o atención general.\n'
                                         '\n'
                                         'No registra citas ni solicitudes: solamente transfiere la '
                                         'conversación.',
                          'schema': {'description': 'Devuelve a Soporte una consulta de ticket o atención '
                                                    'general.\n'
                                                    '\n'
                                                    'No registra citas ni solicitudes: solamente transfiere '
                                                    'la conversación.',
                                     'properties': {'motivo': {'title': 'Motivo', 'type': 'string'}},
                                     'required': ['motivo'],
                                     'title': 'transferir_a_soporte',
                                     'type': 'object'},
                          'call_schema': {'description': 'Devuelve a Soporte una consulta de ticket o '
                                                         'atención general.\n'
                                                         '\n'
                                                         'No registra citas ni solicitudes: solamente '
                                                         'transfiere la conversación.',
                                          'properties': {'motivo': {'title': 'Motivo', 'type': 'string'}},
                                          'required': ['motivo'],
                                          'title': 'transferir_a_soporte',
                                          'type': 'object'}},
 'consultar_estado_ticket': {'description': 'Consulta el estado de un ticket de soporte utilizando su '
                                            'número.',
                             'schema': {'description': 'Consulta el estado de un ticket de soporte '
                                                       'utilizando su número.',
                                        'properties': {'numero_ticket': {'title': 'Numero Ticket',
                                                                         'type': 'integer'}},
                                        'required': ['numero_ticket'],
                                        'title': 'consultar_estado_ticket',
                                        'type': 'object'},
                             'call_schema': {'description': 'Consulta el estado de un ticket de soporte '
                                                            'utilizando su número.',
                                             'properties': {'numero_ticket': {'title': 'Numero Ticket',
                                                                              'type': 'integer'}},
                                             'required': ['numero_ticket'],
                                             'title': 'consultar_estado_ticket',
                                             'type': 'object'}},
 'get_ticket_status': {'description': 'Consulta el estado de un ticket de soporte utilizando su número.',
                       'schema': {'properties': {'ticket_id': {'title': 'Ticket Id', 'type': 'integer'}},
                                  'required': ['ticket_id'],
                                  'title': 'get_ticket_status',
                                  'type': 'object'},
                       'call_schema': {'description': 'Consulta el estado de un ticket de soporte utilizando '
                                                      'su número.',
                                       'properties': {'ticket_id': {'title': 'Ticket Id', 'type': 'integer'}},
                                       'required': ['ticket_id'],
                                       'title': 'get_ticket_status',
                                       'type': 'object'}},
 'transferir_a_tecnico': {'description': 'Transfiere una solicitud al agente Técnico cuando el problema\n'
                                         'requiere diagnóstico o conocimientos técnicos especializados.',
                          'schema': {'description': 'Transfiere una solicitud al agente Técnico cuando el '
                                                    'problema\n'
                                                    'requiere diagnóstico o conocimientos técnicos '
                                                    'especializados.',
                                     'properties': {'motivo': {'title': 'Motivo', 'type': 'string'}},
                                     'required': ['motivo'],
                                     'title': 'transferir_a_tecnico',
                                     'type': 'object'},
                          'call_schema': {'description': 'Transfiere una solicitud al agente Técnico cuando '
                                                         'el problema\n'
                                                         'requiere diagnóstico o conocimientos técnicos '
                                                         'especializados.',
                                          'properties': {'motivo': {'title': 'Motivo', 'type': 'string'}},
                                          'required': ['motivo'],
                                          'title': 'transferir_a_tecnico',
                                          'type': 'object'}},
 'transferir_a_ventas': {'description': 'Transfiere una solicitud al agente de Ventas cuando el usuario\n'
                                        'requiere información comercial, precios o cotizaciones.',
                         'schema': {'description': 'Transfiere una solicitud al agente de Ventas cuando el '
                                                   'usuario\n'
                                                   'requiere información comercial, precios o cotizaciones.',
                                    'properties': {'motivo': {'title': 'Motivo', 'type': 'string'}},
                                    'required': ['motivo'],
                                    'title': 'transferir_a_ventas',
                                    'type': 'object'},
                         'call_schema': {'description': 'Transfiere una solicitud al agente de Ventas cuando '
                                                        'el usuario\n'
                                                        'requiere información comercial, precios o '
                                                        'cotizaciones.',
                                         'properties': {'motivo': {'title': 'Motivo', 'type': 'string'}},
                                         'required': ['motivo'],
                                         'title': 'transferir_a_ventas',
                                         'type': 'object'}},
 'authenticated_ticket_tool': {'description': 'Consulta un ticket existente autorizado por la sesión '
                                              'autenticada.',
                               'call_schema': {'description': 'Consulta un ticket existente autorizado por '
                                                              'la sesión autenticada.',
                                               'properties': {'numero_ticket': {'title': 'Numero Ticket',
                                                                                'type': 'integer'}},
                                               'required': ['numero_ticket'],
                                               'title': 'consultar_estado_ticket',
                                               'type': 'object'}},
 'authenticated_ticket_status_tool': {'description': 'Consulta un ticket existente autorizado por la sesión '
                                                     'autenticada.',
                                      'call_schema': {'description': 'Consulta un ticket existente '
                                                                     'autorizado por la sesión autenticada.',
                                                      'properties': {'ticket_id': {'title': 'Ticket Id',
                                                                                   'type': 'integer'}},
                                                      'required': ['ticket_id'],
                                                      'title': 'get_ticket_status',
                                                      'type': 'object'}}}
