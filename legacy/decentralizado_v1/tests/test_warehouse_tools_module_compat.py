import ast
from copy import deepcopy
from decimal import Decimal
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
from sqlalchemy import text

from test_inventory_matching import inventory
from test_software_e2e import network


ROOT = Path(__file__).resolve().parents[1]
CANONICAL = "app.agents.decentralized.tools.warehouse_tools"
LEGACY = "app.agents.decentralized.tools.almacen_tools"
EXPORTS = ["transferir_a_compras", "consultar_inventario", "check_inventory", "transferir_a_ventas"]
VARIANTS = [("consultar_inventario", "nombre_repuesto", "cantidad"), ("check_inventory", "part_name", "quantity")]


@pytest.mark.parametrize("first", ["warehouse_tools", "almacen_tools"])
@pytest.mark.parametrize("style", ["importlib", "package"])
def test_fresh_import_orders_share_identity_without_querying_repository(first, style):
    script = r'''
import importlib, json, sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock
sys.path.insert(0, sys.argv[1])
repository = ModuleType("app.database.repository")
repository.lookup_inventory = MagicMock(side_effect=AssertionError("No inventory query during import"))
sys.modules["app.database.repository"] = repository
executions = []
def profile(frame, event, arg):
    if event == "call" and frame.f_code.co_name == "<module>" and Path(frame.f_code.co_filename).name == "warehouse_tools.py":
        executions.append(frame.f_code.co_filename)
sys.setprofile(profile)
def load(name):
    if sys.argv[3] == "package":
        namespace = {}
        exec("from app.agents.decentralized.tools import " + name, namespace)
        return namespace[name]
    return importlib.import_module("app.agents.decentralized.tools." + name)
one = load(sys.argv[2])
two = load("almacen_tools" if sys.argv[2] == "warehouse_tools" else "warehouse_tools")
from app.agents.decentralized.tools import warehouse_tools, almacen_tools
assert one is two is warehouse_tools is almacen_tools
assert load("warehouse_tools") is load("almacen_tools") is one
assert one.__name__ == one.__spec__.name == "app.agents.decentralized.tools.warehouse_tools"
assert Path(one.__file__).name == "warehouse_tools.py"
assert one.lookup_inventory is repository.lookup_inventory
repository.lookup_inventory.assert_not_called()
assert len(executions) == 1
assert not any(name.startswith(("app.database.connection", "app.rag", "langchain_groq", "psycopg")) for name in sys.modules)
sys.setprofile(None)
print(json.dumps({"executions": len(executions)}))
'''
    result = subprocess.run([sys.executable, "-B", "-c", script, str(ROOT), first, style],
                            cwd=ROOT, capture_output=True, text=True, timeout=60, check=True)
    assert json.loads(result.stdout) == {"executions": 1}


@pytest.mark.parametrize("name", EXPORTS)
def test_canonical_metadata_decorated_identity_and_frozen_contract(name):
    canonical, legacy = importlib.import_module(CANONICAL), importlib.import_module(LEGACY)
    assert canonical is legacy
    assert canonical.__name__ == canonical.__spec__.name == CANONICAL
    assert Path(canonical.__file__) == ROOT / "app/agents/decentralized/tools/warehouse_tools.py"
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
@pytest.mark.parametrize("attribute", [*EXPORTS, "lookup_inventory"])
def test_bidirectional_monkeypatch_and_restoration(path, attribute, monkeypatch):
    module = importlib.import_module(path)
    peer = importlib.import_module(LEGACY if path == CANONICAL else CANONICAL)
    original = getattr(module, attribute)
    with monkeypatch.context() as patch:
        replacement = MagicMock()
        patch.setattr(module, attribute, replacement)
        assert getattr(peer, attribute) is replacement
    assert getattr(module, attribute) is getattr(peer, attribute) is original


def test_repository_import_is_captured_but_tool_global_is_dynamic(monkeypatch):
    module = importlib.import_module(CANONICAL)
    repository = importlib.import_module("app.database.repository")
    original = module.lookup_inventory
    assert original is repository.lookup_inventory
    assert inspect.getmodule(original) is repository
    with monkeypatch.context() as patch:
        replacement = MagicMock()
        patch.setattr(repository, "lookup_inventory", replacement)
        assert module.lookup_inventory is original
        replacement.assert_not_called()
    assert repository.lookup_inventory is module.lookup_inventory is original


@pytest.mark.parametrize("path", [CANONICAL, LEGACY])
@pytest.mark.parametrize("name,part,quantity", VARIANTS)
def test_mocked_lookup_arguments_and_error_propagation(path, name, part, quantity, monkeypatch):
    module = importlib.import_module(path)
    peer = importlib.import_module(LEGACY if path == CANONICAL else CANONICAL)
    lookup = MagicMock(return_value=dict(unit_price=Decimal("180.00"), stock=3, available=True))
    original = module.lookup_inventory
    with monkeypatch.context() as patch:
        patch.setattr(module, "lookup_inventory", lookup)
        result = getattr(peer, name).invoke({part: "SSD", quantity: 2})
        assert result == dict(unit_price="180.00", stock=3, available=True)
        lookup.assert_called_once_with(requested_name="SSD", quantity=2)
        error = RuntimeError("Controlled repository failure")
        lookup.side_effect = error
        with pytest.raises(RuntimeError) as captured:
            getattr(peer, name).invoke({part: "SSD", quantity: 2})
        assert captured.value is error
    assert module.lookup_inventory is peer.lookup_inventory is original


@pytest.mark.parametrize("name,part,quantity", VARIANTS)
@pytest.mark.parametrize("status", ["available", "insufficient", "not_found", "ambiguous"])
def test_inventory_result_metadata_prices_and_nonmutation(name, part, quantity, status, monkeypatch):
    module = importlib.import_module(CANONICAL)
    found = status in {"available", "insufficient"}
    row = dict(requested_name="SSD", name="SSD", quantity=2, stock=3 if status == "available" else 0,
               unit_price=Decimal("180.00") if found else Decimal("0.00"), found=found,
               available=status == "available", inventory_id=1 if found else None,
               metadata={"source": "fixture"})
    if not found:
        row["match_status"] = status
    before = deepcopy(row)
    lookup = MagicMock(return_value=row)
    monkeypatch.setattr(module, "lookup_inventory", lookup)
    result = getattr(module, name).invoke({part: "SSD", quantity: 2})
    assert result == {**before, "unit_price": str(before["unit_price"])}
    assert row == before and result is not row
    lookup.assert_called_once_with(requested_name="SSD", quantity=2)


@pytest.mark.parametrize("name,part,quantity", VARIANTS)
@pytest.mark.parametrize("arguments", ["empty", "zero"])
def test_invalid_request_never_calls_lookup(name, part, quantity, arguments, monkeypatch):
    module = importlib.import_module(CANONICAL)
    lookup = MagicMock()
    monkeypatch.setattr(module, "lookup_inventory", lookup)
    with pytest.raises(ValueError):
        getattr(module, name).invoke({part: " " if arguments == "empty" else "SSD", quantity: 0 if arguments == "zero" else 1})
    lookup.assert_not_called()


def test_agent_and_toolnode_capture_same_inventory_tools(network, monkeypatch):
    graph_module, _ = network
    module = importlib.import_module(CANONICAL)
    legacy = importlib.import_module(LEGACY)
    agent = importlib.import_module("app.agents.decentralized.warehouse")
    assert module is legacy
    assert agent.warehouse_tools is agent.almacen_tools is graph_module.warehouse_tools
    assert [tool.name for tool in agent.warehouse_tools] == ["check_inventory", "transfer_to_sales", "transfer_to_purchasing"]
    assert agent.check_inventory is module.check_inventory
    registered = graph_module.build_graph().get_graph().nodes["almacen_tools"].data.tools_by_name
    assert registered["check_inventory"] is module.check_inventory
    assert registered["consultar_inventario"] is graph_module.consultar_inventario is module.consultar_inventario
    captured = module.check_inventory
    with monkeypatch.context() as patch:
        patch.setattr(module, "check_inventory", MagicMock())
        assert agent.check_inventory is registered["check_inventory"] is captured
    assert module.check_inventory is captured


@pytest.mark.parametrize("name,part,quantity", VARIANTS)
@pytest.mark.parametrize("stock,destination", [(3, "ventas"), (0, "compras"), (1, "compras")])
def test_checkpoint_inventory_routes_to_sales_or_purchasing(network, name, part, quantity, stock, destination):
    graph_module, controls = network
    controls["inventory_stock"] = stock
    event = AIMessage(content="", id="inventory", tool_calls=[dict(name=name,
        args={part: "SSD de prueba", quantity: 2}, id="inventory-call")])
    before = deepcopy(event)
    config = {"configurable": {"thread_id": "warehouse-tools-module"}}
    saver = MemorySaver()
    graph_module.build_graph(checkpointer=saver).update_state(config, dict(
        messages=[HumanMessage(content="Consultar dos SSD de prueba"), event], current_agent="almacen",
        request_revision=2, inventory_requested_by="ventas", required_parts=[dict(name="SSD de prueba", quantity=2)],
        handoff_count=0, handoff_history=[], handoff_records=[]), as_node="almacen")
    result = graph_module.build_graph(checkpointer=saver).invoke(None, config, interrupt_after=["auditar_almacen"])
    outputs = [message for message in result["messages"] if isinstance(message, ToolMessage)]
    assert [(message.name, message.tool_call_id) for message in outputs] == [(name, "inventory-call")]
    assert outputs[0].status != "error"
    assert controls["inventory_calls"] == [("SSD de prueba", 2)]
    assert result["inventory_revision"] == 2
    assert result["inventory_results"][0]["stock"] == stock
    assert result["inventory_results"][0]["unit_price"] == "180.00"
    assert result["handoff_history"] == [{"origin": "almacen", "destination": destination}]
    assert result["handoff_count"] == 1
    assert event == before
    assert not result.get("quote_id") and not result.get("payment_id")


@pytest.mark.parametrize("active", [True, False])
def test_isolated_sqlite_lookup_preserves_active_filter(inventory, active, monkeypatch):
    lookup, engine = inventory
    with engine.begin() as connection:
        connection.execute(text("UPDATE spare_parts SET active = :active"), {"active": active})
    module = importlib.import_module(CANONICAL)
    monkeypatch.setattr(module, "lookup_inventory", lambda requested_name, quantity: lookup(requested_name, quantity, engine))
    result = module.check_inventory.invoke({"part_name": "SSD 500GB NVMe", "quantity": 2})
    assert result["found"] is active and result["available"] is active
    assert result["inventory_id"] == (1 if active else None)
    assert Decimal(result["unit_price"]) == (Decimal("180") if active else Decimal("0"))


def test_legacy_shim_and_single_canonical_ast():
    legacy = (ROOT / "app/agents/decentralized/tools/almacen_tools.py").read_text(encoding="utf-8")
    assert '".warehouse_tools"' in legacy
    assert not any(isinstance(node, (ast.FunctionDef, ast.ClassDef)) for node in ast.parse(legacy).body)
    tree = ast.parse((ROOT / "app/agents/decentralized/tools/warehouse_tools.py").read_text(encoding="utf-8"))
    assert {node.name for node in tree.body if isinstance(node, ast.FunctionDef)} == {
        "transferir_a_compras", "consultar_inventario", "_check_inventory", "transferir_a_ventas"}


ORIGINAL_CONTRACTS = {'transferir_a_compras': {'description': 'Deriva faltantes confirmados a Compras, sin crear pedidos.',
                          'schema': {'description': 'Deriva faltantes confirmados a Compras, sin crear '
                                                    'pedidos.',
                                     'properties': {'motivo': {'title': 'Motivo', 'type': 'string'}},
                                     'required': ['motivo'],
                                     'title': 'transferir_a_compras',
                                     'type': 'object'},
                          'call_schema': {'description': 'Deriva faltantes confirmados a Compras, sin crear '
                                                         'pedidos.',
                                          'properties': {'motivo': {'title': 'Motivo', 'type': 'string'}},
                                          'required': ['motivo'],
                                          'title': 'transferir_a_compras',
                                          'type': 'object'}},
 'consultar_inventario': {'description': 'Consulta en PostgreSQL el stock y precio de un repuesto.',
                          'schema': {'description': 'Consulta en PostgreSQL el stock y precio de un '
                                                    'repuesto.',
                                     'properties': {'nombre_repuesto': {'title': 'Nombre Repuesto',
                                                                        'type': 'string'},
                                                    'cantidad': {'default': 1,
                                                                 'title': 'Cantidad',
                                                                 'type': 'integer'}},
                                     'required': ['nombre_repuesto'],
                                     'title': 'consultar_inventario',
                                     'type': 'object'},
                          'call_schema': {'description': 'Consulta en PostgreSQL el stock y precio de un '
                                                         'repuesto.',
                                          'properties': {'nombre_repuesto': {'title': 'Nombre Repuesto',
                                                                             'type': 'string'},
                                                         'cantidad': {'default': 1,
                                                                      'title': 'Cantidad',
                                                                      'type': 'integer'}},
                                          'required': ['nombre_repuesto'],
                                          'title': 'consultar_inventario',
                                          'type': 'object'}},
 'check_inventory': {'description': 'Consulta en PostgreSQL el stock y precio de un repuesto.',
                     'schema': {'properties': {'part_name': {'title': 'Part Name', 'type': 'string'},
                                               'quantity': {'default': 1,
                                                            'title': 'Quantity',
                                                            'type': 'integer'}},
                                'required': ['part_name'],
                                'title': 'check_inventory',
                                'type': 'object'},
                     'call_schema': {'description': 'Consulta en PostgreSQL el stock y precio de un '
                                                    'repuesto.',
                                     'properties': {'part_name': {'title': 'Part Name', 'type': 'string'},
                                                    'quantity': {'default': 1,
                                                                 'title': 'Quantity',
                                                                 'type': 'integer'}},
                                     'required': ['part_name'],
                                     'title': 'check_inventory',
                                     'type': 'object'}},
 'transferir_a_ventas': {'description': 'Transfiere a Ventas los resultados del inventario.',
                         'schema': {'description': 'Transfiere a Ventas los resultados del inventario.',
                                    'properties': {'motivo': {'title': 'Motivo', 'type': 'string'}},
                                    'required': ['motivo'],
                                    'title': 'transferir_a_ventas',
                                    'type': 'object'},
                         'call_schema': {'description': 'Transfiere a Ventas los resultados del inventario.',
                                         'properties': {'motivo': {'title': 'Motivo', 'type': 'string'}},
                                         'required': ['motivo'],
                                         'title': 'transferir_a_ventas',
                                         'type': 'object'}}}
