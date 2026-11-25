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
ENGLISH = "app.agents.decentralized.sales"
LEGACY = "app.agents.decentralized.ventas"


@pytest.mark.parametrize("first", ["sales", "ventas"])
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
        bindings.append((tools, kwargs, bound))
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
two = load("ventas" if sys.argv[2] == "sales" else "sales")
from app.agents.decentralized import sales, ventas
assert one is two is sales is ventas
assert load("sales") is load("ventas") is one
assert len(created) == len(bindings) == 1
assert dotenv_calls.count("app.agents.decentralized.sales") == 1
assert created == [dict(model="openai/gpt-oss-20b", temperature=0,
    reasoning_effort="low", model_kwargs={"parallel_tool_calls": False, "tool_choice": "auto"})]
assert bindings[0][0] is one.sales_tools is one.ventas_tools
assert bindings[0][1] == {}
assert bindings[0][2] is one.sales_llm is one.ventas_llm is one._INITIAL_SALES_LLM
assert one._resolve_sales_llm() is one.sales_llm
assert one.sales_node is one.ventas_node
assert sys.modules["app.agents.decentralized.sales"] is sys.modules["app.agents.decentralized.ventas"]
assert one.__name__ == one.__spec__.name == "app.agents.decentralized.sales"
assert Path(one.__file__).name == "sales.py"
if sys.argv[4] == "reload":
    captured_node, captured_model, captured_tools = one.sales_node, one.sales_llm, one.sales_tools
    reloaded = importlib.reload(one)
    assert reloaded is one is load("sales") is load("ventas")
    assert len(created) == len(bindings) == 2 and created[-1] == created[0]
    assert bindings[-1][1] == {}
    assert one.sales_llm is one.ventas_llm is one._INITIAL_SALES_LLM is one._resolve_sales_llm()
    assert captured_node is not one.sales_node and captured_model is not one.sales_llm
    assert captured_tools is not one.sales_tools
    assert one.sales_tools is one.ventas_tools is bindings[-1][0]
    assert captured_node.__globals__ is one.sales_node.__globals__ is one.__dict__
print(json.dumps({"created": len(created), "bindings": len(bindings)}))
'''
    result = subprocess.run([sys.executable, "-B", "-c", script, str(ROOT), first, style, "reload" if reload_requested else "normal"],
                            cwd=ROOT, capture_output=True, text=True, timeout=60, check=True)
    assert json.loads(result.stdout) == {"created": 2 if reload_requested else 1, "bindings": 2 if reload_requested else 1}


def test_identity_globals_metadata_and_graph_capture(network):
    graph_module, _ = network
    english, legacy = importlib.import_module(ENGLISH), importlib.import_module(LEGACY)
    from app.agents.decentralized import sales, ventas
    assert english is legacy is sales is ventas
    assert english.sales_node is legacy.ventas_node is graph_module.AGENT_NODES["ventas"]
    assert english.sales_node.__globals__ is legacy.__dict__
    assert english.sales_tools is legacy.ventas_tools is graph_module.sales_tools
    assert english.sales_llm is legacy.ventas_llm is english._INITIAL_SALES_LLM
    assert english.__name__ == english.__spec__.name == ENGLISH
    assert Path(english.__file__) == ROOT / "app/agents/decentralized/sales.py"
    assert english.sales_node.__module__ == ENGLISH
    assert inspect.getmodule(english.sales_node) is legacy
    assert inspect.getsourcefile(english.sales_node) == legacy.__file__
    assert "def sales_node(" in inspect.getsource(english.sales_node)


@pytest.mark.parametrize("path", [ENGLISH, LEGACY])
@pytest.mark.parametrize("attribute", ["sales_llm", "ventas_llm"])
def test_model_monkeypatch_invokes_from_other_path_and_restores(network, monkeypatch, path, attribute):
    source = importlib.import_module(path)
    peer = importlib.import_module(LEGACY if path == ENGLISH else ENGLISH)
    original = source._resolve_sales_llm()
    model = MagicMock()
    response = AIMessage(content="", tool_calls=[dict(name="identify_quote_service", args={"service": "revision"}, id="service")])
    model.invoke.return_value = response
    with monkeypatch.context() as patch:
        patch.setattr(source, attribute, model)
        assert getattr(peer, attribute) is model
        assert peer._resolve_sales_llm() is model
        result = peer.sales_node({"messages": [HumanMessage(content="Consulta general")]})
        assert result["messages"][0] is response
        model.invoke.assert_called_once()
    assert source._resolve_sales_llm() is peer._resolve_sales_llm() is original


@pytest.mark.parametrize("path", [ENGLISH, LEGACY])
@pytest.mark.parametrize("attribute", ["sales_tools", "ventas_tools", "sales_node", "ventas_node"])
def test_exports_monkeypatch_is_shared_but_graph_keeps_captured_reference(network, monkeypatch, path, attribute):
    graph_module, _ = network
    source, peer = importlib.import_module(path), importlib.import_module(LEGACY if path == ENGLISH else ENGLISH)
    original = getattr(source, attribute)
    captured = graph_module.AGENT_NODES["ventas"] if attribute.endswith("node") else graph_module.sales_tools
    replacement = [] if attribute.endswith("tools") else lambda state: {}
    with monkeypatch.context() as patch:
        patch.setattr(source, attribute, replacement)
        assert getattr(peer, attribute) is replacement
        assert (graph_module.AGENT_NODES["ventas"] if attribute.endswith("node") else graph_module.sales_tools) is captured
    assert getattr(source, attribute) is getattr(peer, attribute) is original


@pytest.mark.parametrize("path", [ENGLISH, LEGACY])
def test_unconfirmed_inventory_guard_precedes_model(network, monkeypatch, path):
    agent = importlib.import_module(path)
    forbidden = MagicMock()
    forbidden.invoke.side_effect = AssertionError("No model before commercial validation")
    monkeypatch.setattr(agent, "sales_llm", forbidden)
    result = agent.sales_node(dict(messages=[HumanMessage(content="Consulta general")], inventory_pending=True))
    forbidden.invoke.assert_not_called()
    assert result["quote"]["total"] is None
    assert not result.get("quote_id") and not result.get("payment_id")


@pytest.mark.parametrize("stock", [1, 3])
def test_inventory_quantity_and_price_preserved_without_model(network, monkeypatch, stock):
    from copy import deepcopy
    from decimal import Decimal
    agent = importlib.import_module(ENGLISH)
    item = dict(tool_call_id="inventory", requested_name="SSD de prueba", name="SSD de prueba",
                quantity=2, stock=stock, unit_price="180.00", available=stock >= 2, found=True)
    state = dict(messages=[HumanMessage(content="Cotiza el repuesto")], quote_scope="repuestos", inventory_results=[item])
    before = deepcopy(state)
    model = MagicMock()
    monkeypatch.setattr(agent, "sales_llm", model)
    inventory, errors = agent.validate_inventory(state)
    assert errors == [] and inventory[0]["quantity"] == 2
    assert Decimal(inventory[0]["unit_price"]) == Decimal("180.00")
    assert inventory[0]["subtotal"] == ("360.00" if stock >= 2 else None)
    result = agent.sales_node(state)
    model.invoke.assert_not_called()
    assert state == before and result["quote"]["total"] is None
    if stock >= 2:
        assert result["quote"]["known_parts_subtotal"] == "360.00"
    assert not result.get("quote_id") and not result.get("payment_id")


@pytest.mark.parametrize("tool_name", ["request_inventory", "solicitar_inventario"])
def test_inventory_request_resume_preserves_handoff_and_call_id(network, tool_name):
    graph_module, _ = network
    event = AIMessage(content="", id="event", tool_calls=[dict(name=tool_name,
        args={"query" if tool_name == "request_inventory" else "consulta": "Consultar SSD de prueba"}, id="inventory")])
    saver = MemorySaver()
    config = {"configurable": {"thread_id": "sales-inventory"}}
    state = dict(messages=[HumanMessage(content="Consulta"), event], current_agent="ventas",
                 handoff_history=[], handoff_records=[], handoff_count=0)
    graph_module.build_graph(checkpointer=saver).update_state(config, state, as_node="ventas")
    result = graph_module.build_graph(checkpointer=saver).invoke(None, config, interrupt_after=["auditar_ventas"])
    outputs = [m for m in result["messages"] if isinstance(m, ToolMessage)]
    assert [(m.name, m.tool_call_id) for m in outputs] == [(tool_name, "inventory")]
    assert outputs[0].status != "error"
    assert result["handoff_history"] == [{"origin": "ventas", "destination": "almacen"}]
    assert result["handoff_count"] == 1


@pytest.mark.parametrize("tool_name", ["transfer_to_support", "transferir_a_soporte"])
def test_checkpoint_resume_observes_english_model_patch_and_historical_calls(network, monkeypatch, tool_name):
    graph_module, _ = network
    agent = importlib.import_module(ENGLISH)
    event = AIMessage(content="", id="event", tool_calls=[dict(name=tool_name,
        args={"reason" if tool_name == "transfer_to_support" else "motivo": "Evaluar"}, id="call")])
    model = MagicMock()
    model.invoke.return_value = event
    monkeypatch.setattr(agent, "sales_llm", model)
    saver = MemorySaver()
    config = {"configurable": {"thread_id": "sales-module"}}
    graph_module.build_graph(checkpointer=saver).update_state(config,
        dict(messages=[HumanMessage(content="Consulta general", id="human")], current_agent="ventas",
             handoff_count=0, handoff_history=[], handoff_records=[], request_revision=2), as_node="preparar_turno")
    result = graph_module.build_graph(checkpointer=saver).invoke(None, config, interrupt_after=["auditar_ventas"])
    model.invoke.assert_called_once()
    outputs = [m for m in result["messages"] if isinstance(m, ToolMessage)]
    assert [(m.name, m.tool_call_id) for m in outputs] == [(tool_name, "call")]
    assert result["handoff_history"] == [{"origin": "ventas", "destination": "soporte"}]
    assert result["handoff_count"] == 1


def test_canonical_file_contains_implementation_and_legacy_only_aliases():
    import ast
    source = (ROOT / "app/agents/decentralized/ventas.py").read_text(encoding="utf-8")
    assert not any(isinstance(node, (ast.FunctionDef, ast.ClassDef)) for node in ast.parse(source).body)
    assert '".sales"' in source
    canonical = (ROOT / "app/agents/decentralized/sales.py").read_text(encoding="utf-8")
    tree = ast.parse(canonical)
    assert [node.name for node in tree.body if isinstance(node, ast.FunctionDef)] == ["_resolve_sales_llm", "validate_inventory", "build_inventory_context", "build_sales_context", "sales_node"]
    assert sum(isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "ChatGroq" for node in ast.walk(tree)) == 1
    assert sum(isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "bind_tools" for node in ast.walk(tree)) == 1


@pytest.mark.parametrize("path", [ENGLISH, LEGACY])
def test_conflicting_models_fail_without_invocation_and_restore(network, monkeypatch, path):
    agent = importlib.import_module(path)
    original = agent._resolve_sales_llm()
    first, second = MagicMock(), MagicMock()
    with monkeypatch.context() as patch:
        patch.setattr(agent, "sales_llm", first)
        patch.setattr(agent, "ventas_llm", second)
        with pytest.raises(ValueError, match="Conflicting sales models"):
            agent._resolve_sales_llm()
        first.invoke.assert_not_called()
        second.invoke.assert_not_called()
    assert agent._resolve_sales_llm() is original
