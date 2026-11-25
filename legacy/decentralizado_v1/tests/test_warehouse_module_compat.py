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
ENGLISH = "app.agents.decentralized.warehouse"
LEGACY = "app.agents.decentralized.almacen"


@pytest.mark.parametrize("first", ["warehouse", "almacen"])
@pytest.mark.parametrize("style", ["importlib", "package"])
@pytest.mark.parametrize("reload_requested", [False, True])
def test_fresh_import_orders_initialize_and_bind_once(first, style, reload_requested):
    script = r'''
import importlib, json, sys
from pathlib import Path
from types import ModuleType
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
def load(name):
    if sys.argv[3] == "package":
        namespace = {}
        exec("from app.agents.decentralized import " + name, namespace)
        return namespace[name]
    return importlib.import_module("app.agents.decentralized." + name)
one = load(sys.argv[2])
two = load("almacen" if sys.argv[2] == "warehouse" else "warehouse")
from app.agents.decentralized import warehouse, almacen
assert one is two is warehouse is almacen
assert load("warehouse") is load("almacen") is one
assert len(created) == len(bindings) == 1
assert dotenv_calls.count("app.agents.decentralized.warehouse") == 1
assert created == [dict(model="openai/gpt-oss-20b", temperature=0,
    reasoning_effort="low", model_kwargs={"parallel_tool_calls": False})]
assert bindings[0][0] is one.warehouse_tools is one.almacen_tools
assert bindings[0][1] == {}
assert bindings[0][2] is one.warehouse_llm is one.almacen_llm is one._INITIAL_WAREHOUSE_LLM
assert one._resolve_warehouse_llm() is one.warehouse_llm
assert one.warehouse_node is one.almacen_node
assert sys.modules["app.agents.decentralized.warehouse"] is sys.modules["app.agents.decentralized.almacen"]
assert one.__name__ == one.__spec__.name == "app.agents.decentralized.warehouse"
assert Path(one.__file__).name == "warehouse.py"
if sys.argv[4] == "reload":
    captured_node, captured_model, captured_tools = one.warehouse_node, one.warehouse_llm, one.warehouse_tools
    reloaded = importlib.reload(one)
    assert reloaded is one is load("warehouse") is load("almacen")
    assert len(created) == len(bindings) == 2
    assert one.warehouse_llm is one.almacen_llm is one._INITIAL_WAREHOUSE_LLM is one._resolve_warehouse_llm()
    assert captured_node is not one.warehouse_node and captured_model is not one.warehouse_llm
    assert captured_tools is not one.warehouse_tools
    assert one.warehouse_tools is one.almacen_tools is bindings[-1][0]
    assert captured_node.__globals__ is one.warehouse_node.__globals__ is one.__dict__
print(json.dumps({"created": len(created), "bindings": len(bindings)}))
'''
    result = subprocess.run([sys.executable, "-B", "-c", script, str(ROOT), first, style, "reload" if reload_requested else "normal"],
                            cwd=ROOT, capture_output=True, text=True, timeout=60, check=True)
    assert json.loads(result.stdout) == {"created": 2 if reload_requested else 1, "bindings": 2 if reload_requested else 1}


def test_identity_globals_metadata_and_graph_capture(network):
    graph_module, _ = network
    english, legacy = importlib.import_module(ENGLISH), importlib.import_module(LEGACY)
    from app.agents.decentralized import warehouse, almacen
    assert english is legacy is warehouse is almacen
    assert english.warehouse_node is legacy.almacen_node is graph_module.AGENT_NODES["almacen"]
    assert english.warehouse_node.__globals__ is legacy.__dict__
    assert english.warehouse_tools is legacy.almacen_tools is graph_module.warehouse_tools
    assert english.warehouse_llm is legacy.almacen_llm is english._INITIAL_WAREHOUSE_LLM
    assert english.__name__ == english.__spec__.name == ENGLISH
    assert Path(english.__file__) == ROOT / "app/agents/decentralized/warehouse.py"
    assert english.warehouse_node.__module__ == ENGLISH
    assert inspect.getmodule(english.warehouse_node) is legacy
    assert inspect.getsourcefile(english.warehouse_node) == legacy.__file__
    assert "def warehouse_node(" in inspect.getsource(english.warehouse_node)


@pytest.mark.parametrize("path", [ENGLISH, LEGACY])
@pytest.mark.parametrize("attribute", ["warehouse_llm", "almacen_llm"])
def test_model_monkeypatch_invokes_from_other_path_and_restores(network, monkeypatch, path, attribute):
    source = importlib.import_module(path)
    peer = importlib.import_module(LEGACY if path == ENGLISH else ENGLISH)
    original = source._resolve_warehouse_llm()
    model = MagicMock()
    response = AIMessage(content="Controlled response")
    model.invoke.return_value = response
    with monkeypatch.context() as patch:
        patch.setattr(source, attribute, model)
        assert getattr(peer, attribute) is model
        assert peer._resolve_warehouse_llm() is model
        result = peer.warehouse_node({"messages": [HumanMessage(content="Consulta general")]})
        assert result["messages"][0] is response
        model.invoke.assert_called_once()
    assert source._resolve_warehouse_llm() is peer._resolve_warehouse_llm() is original


@pytest.mark.parametrize("path", [ENGLISH, LEGACY])
@pytest.mark.parametrize("attribute", ["warehouse_tools", "almacen_tools", "warehouse_node", "almacen_node"])
def test_exports_monkeypatch_is_shared_but_graph_keeps_captured_reference(network, monkeypatch, path, attribute):
    graph_module, _ = network
    source, peer = importlib.import_module(path), importlib.import_module(LEGACY if path == ENGLISH else ENGLISH)
    original = getattr(source, attribute)
    captured = graph_module.AGENT_NODES["almacen"] if attribute.endswith("node") else graph_module.warehouse_tools
    replacement = [] if attribute.endswith("tools") else lambda state: {}
    with monkeypatch.context() as patch:
        patch.setattr(source, attribute, replacement)
        assert getattr(peer, attribute) is replacement
        assert (graph_module.AGENT_NODES["almacen"] if attribute.endswith("node") else graph_module.warehouse_tools) is captured
    assert getattr(source, attribute) is getattr(peer, attribute) is original


@pytest.mark.parametrize("path", [ENGLISH, LEGACY])
def test_structured_inventory_precedes_model_and_preserves_tool_arguments(network, monkeypatch, path):
    graph_module, controls = network
    agent = importlib.import_module(path)
    model = MagicMock(side_effect=AssertionError("No model before inventory"))
    monkeypatch.setattr(agent, "warehouse_llm", model)
    state = dict(messages=[HumanMessage(content="Consulta")], request_revision=2,
                 required_parts=[{"name": "SSD de prueba", "quantity": 2}])
    result = agent.warehouse_node(state)
    call = result["messages"][0].tool_calls[0]
    assert call["name"] == "check_inventory" and call["args"] == {"part_name": "SSD de prueba", "quantity": 2}
    assert controls["inventory_calls"] == []
    model.invoke.assert_not_called()
    tools = graph_module.build_graph().get_graph().nodes["almacen_tools"].data.tools_by_name
    original = next(tool for tool in agent.warehouse_tools if tool.name == "check_inventory")
    assert tools["check_inventory"] is original
    output = original.invoke(call["args"])
    assert controls["inventory_calls"] == [("SSD de prueba", 2)]
    assert output["stock"] == 3 and output["available"] is True and output["unit_price"] == "180.00"


@pytest.mark.parametrize("stock,destination", [(0,"transfer_to_purchasing"), (1,"transfer_to_purchasing"), (3,"transfer_to_sales")])
def test_confirmed_stock_preserves_handoff_without_model_or_inventory_requery(network, monkeypatch, stock, destination):
    from copy import deepcopy
    from test_compras import value
    agent = importlib.import_module(ENGLISH)
    state = value(stock=stock, quantity=2)
    before = deepcopy(state)
    model = MagicMock()
    monkeypatch.setattr(agent, "warehouse_llm", model)
    result = agent.warehouse_node(state)
    assert result["messages"][0].tool_calls[0]["name"] == destination
    assert state == before
    model.invoke.assert_not_called()
    assert network[1]["inventory_calls"] == []


@pytest.mark.parametrize("tool_name", ["transfer_to_sales", "transferir_a_ventas", "transfer_to_purchasing", "transferir_a_compras"])
def test_checkpoint_resume_observes_english_model_patch_and_historical_calls(network, monkeypatch, tool_name):
    graph_module, _ = network
    agent = importlib.import_module(ENGLISH)
    event = AIMessage(content="", id="event", tool_calls=[dict(name=tool_name,
        args={"reason" if tool_name.startswith("transfer_to_") else "motivo": "Evaluar"}, id="call")])
    model = MagicMock()
    model.invoke.return_value = event
    monkeypatch.setattr(agent, "warehouse_llm", model)
    saver = MemorySaver()
    config = {"configurable": {"thread_id": "warehouse-module"}}
    from test_compras import value
    purchasing = tool_name in {"transfer_to_purchasing", "transferir_a_compras"}
    state = value(stock=0 if purchasing else 3, quantity=2)
    state.update(messages=[HumanMessage(content="Consulta general", id="human"), event], current_agent="almacen",
                 handoff_count=0, handoff_history=[], handoff_records=[], inventory_pending=False,
                 inventory_requested_by="ventas")
    graph_module.build_graph(checkpointer=saver).update_state(config, state, as_node="almacen")
    result = graph_module.build_graph(checkpointer=saver).invoke(None, config, interrupt_after=["auditar_almacen"])
    model.invoke.assert_not_called()
    outputs = [m for m in result["messages"] if isinstance(m, ToolMessage)]
    assert [(m.name, m.tool_call_id) for m in outputs] == [(tool_name, "call")]
    assert result["handoff_history"] == [{"origin": "almacen", "destination": "compras" if tool_name in {"transfer_to_purchasing", "transferir_a_compras"} else "ventas"}]
    assert result["handoff_count"] == 1


def test_canonical_file_contains_implementation_and_legacy_only_aliases():
    import ast
    source = (ROOT / "app/agents/decentralized/almacen.py").read_text(encoding="utf-8")
    assert not any(isinstance(node, (ast.FunctionDef, ast.ClassDef)) for node in ast.parse(source).body)
    assert '".warehouse"' in source
    canonical = (ROOT / "app/agents/decentralized/warehouse.py").read_text(encoding="utf-8")
    tree = ast.parse(canonical)
    assert [node.name for node in tree.body if isinstance(node, ast.FunctionDef)] == ["_resolve_warehouse_llm", "build_warehouse_context", "warehouse_node"]
    assert sum(isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "ChatGroq" for node in ast.walk(tree)) == 1
    assert sum(isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "bind_tools" for node in ast.walk(tree)) == 1


@pytest.mark.parametrize("path", [ENGLISH, LEGACY])
def test_conflicting_models_fail_without_invocation_and_restore(network, monkeypatch, path):
    agent = importlib.import_module(path)
    original = agent._resolve_warehouse_llm()
    first, second = MagicMock(), MagicMock()
    with monkeypatch.context() as patch:
        patch.setattr(agent, "warehouse_llm", first)
        patch.setattr(agent, "almacen_llm", second)
        with pytest.raises(ValueError, match="Conflicting warehouse models"):
            agent._resolve_warehouse_llm()
        first.invoke.assert_not_called()
        second.invoke.assert_not_called()
    assert agent._resolve_warehouse_llm() is original
