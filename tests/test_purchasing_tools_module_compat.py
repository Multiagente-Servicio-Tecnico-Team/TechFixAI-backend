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

from test_compras import value
from test_software_e2e import network


ROOT = Path(__file__).resolve().parents[1]
PREFIX = "app.agents.decentralized.tools."
CANONICAL = PREFIX + "purchasing_tools"
LEGACY = PREFIX + "compras_tools"
EXPORTS = ["consultar_fuentes_abastecimiento", "get_sourcing_capabilities", "transferir_a_ventas"]


@pytest.mark.parametrize("first", ["compras_tools", "purchasing_tools"])
@pytest.mark.parametrize("style", ["importlib", "package"])
def test_fresh_import_orders_share_identity_and_single_execution(first, style):
    script = r'''
import importlib, json, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
executions = []
def profile(frame, event, arg):
    if event == "call" and frame.f_code.co_name == "<module>" and Path(frame.f_code.co_filename).name == "purchasing_tools.py":
        executions.append(frame.f_code.co_filename)
sys.setprofile(profile)
def load(name):
    if sys.argv[3] == "package":
        namespace = {}
        exec("from app.agents.decentralized.tools import " + name, namespace)
        return namespace[name]
    return importlib.import_module("app.agents.decentralized.tools." + name)
one = load(sys.argv[2])
two = load("compras_tools" if sys.argv[2] == "purchasing_tools" else "purchasing_tools")
from app.agents.decentralized.tools import compras_tools, purchasing_tools
assert one is two is compras_tools is purchasing_tools
assert load("compras_tools") is load("purchasing_tools") is one
assert len(executions) == 1
assert one.__name__ == one.__spec__.name == "app.agents.decentralized.tools.purchasing_tools"
assert Path(one.__file__).name == "purchasing_tools.py"
assert one.get_sourcing_capabilities.func is one.consultar_fuentes_abastecimiento.func
assert one.transferir_a_ventas.func.__globals__ is one.__dict__
assert not any(name.startswith(("app.database", "app.rag", "langchain_groq", "psycopg")) for name in sys.modules)
sys.setprofile(None)
print(json.dumps({"executions": len(executions)}))
'''
    result = subprocess.run([sys.executable, "-B", "-c", script, str(ROOT), first, style],
                            cwd=ROOT, capture_output=True, text=True, timeout=60, check=True)
    assert json.loads(result.stdout) == {"executions": 1}


def test_metadata_decorated_functions_and_source():
    canonical = importlib.import_module(CANONICAL)
    legacy = importlib.import_module(LEGACY)
    assert canonical is legacy
    assert canonical.__name__ == canonical.__spec__.name == CANONICAL
    assert Path(canonical.__file__) == ROOT / "app/agents/decentralized/tools/purchasing_tools.py"
    for name in EXPORTS:
        tool = getattr(canonical, name)
        assert tool is getattr(legacy, name)
        assert tool.func.__module__ == CANONICAL
        assert tool.func.__globals__ is canonical.__dict__
        assert inspect.getmodule(tool.func) is canonical
        assert inspect.getsourcefile(tool.func) == canonical.__file__
    assert "def transferir_a_ventas(" in inspect.getsource(canonical.transferir_a_ventas.func)


@pytest.mark.parametrize("name", EXPORTS)
def test_public_schema_description_and_results_are_preserved(name):
    module = importlib.import_module(CANONICAL)
    tool = getattr(module, name)
    schema = tool.tool_call_schema.model_json_schema()
    assert tool.name == name
    assert set(schema["properties"]) == ({"motivo"} if name == "transferir_a_ventas" else set())
    assert schema.get("required", []) == (["motivo"] if name == "transferir_a_ventas" else [])
    if name == "transferir_a_ventas":
        assert schema["properties"]["motivo"]["type"] == "string"
        assert tool.invoke({"motivo": "  Faltante confirmado  "}) == "TRANSFERIR_VENTAS: Faltante confirmado"
        with pytest.raises(ValueError, match="Motivo de transferencia obligatorio"):
            tool.invoke({"motivo": " "})
    else:
        assert tool.invoke({}) == {"integration_available": False,
            "missing_fields": ["proveedor asociado verificado", "oferta vigente", "costo", "moneda", "plazo confirmado"]}
    tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
    source_name = "consultar_fuentes_abastecimiento" if name == "get_sourcing_capabilities" else name
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == source_name)
    assert tool.description == ast.get_docstring(function)
    assert module.get_sourcing_capabilities.args_schema is module.consultar_fuentes_abastecimiento.args_schema
    assert module.get_sourcing_capabilities.func is module.consultar_fuentes_abastecimiento.func


@pytest.mark.parametrize("path", [CANONICAL, LEGACY])
@pytest.mark.parametrize("attribute", ["_sales", *EXPORTS])
def test_bidirectional_monkeypatch_and_restoration(path, attribute, monkeypatch):
    module = importlib.import_module(path)
    peer = importlib.import_module(LEGACY if path == CANONICAL else CANONICAL)
    original = getattr(module, attribute)
    replacement = MagicMock()
    replacement.invoke.return_value = "Controlled handoff"
    with monkeypatch.context() as patch:
        patch.setattr(module, attribute, replacement)
        assert getattr(peer, attribute) is replacement
        if attribute == "_sales":
            assert peer.transferir_a_ventas.invoke({"motivo": " Evaluar "}) == "Controlled handoff"
            replacement.invoke.assert_called_once_with({"motivo": "Evaluar"})
    assert getattr(module, attribute) is getattr(peer, attribute) is original


def test_agent_graph_and_handoff_keep_captured_tools(network, monkeypatch):
    graph_module, _ = network
    module = importlib.import_module(CANONICAL)
    agent = importlib.import_module("app.agents.decentralized.purchasing")
    handoffs = importlib.import_module(PREFIX + "purchasing_handoff_tools")
    assert agent.purchasing_tools is agent.compras_tools is graph_module.purchasing_tools
    assert agent.purchasing_tools[0] is module.get_sourcing_capabilities
    assert handoffs._sales is handoffs.legacy_handoff_tools[0] is module.transferir_a_ventas
    registered = graph_module.build_graph().get_graph().nodes["compras_tools"].data.tools_by_name
    assert set(registered) == {*EXPORTS, "transfer_to_sales"}
    assert all(registered[name] is getattr(module, name) for name in EXPORTS)
    captured = agent.purchasing_tools[0]
    with monkeypatch.context() as patch:
        patch.setattr(module, "get_sourcing_capabilities", MagicMock())
        assert agent.purchasing_tools[0] is captured
    assert module.get_sourcing_capabilities is captured


@pytest.mark.parametrize("names", [
    ["get_sourcing_capabilities"], ["consultar_fuentes_abastecimiento"],
    ["get_sourcing_capabilities", "consultar_fuentes_abastecimiento"],
    ["transfer_to_sales"], ["transferir_a_ventas"],
    ["transfer_to_sales", "transferir_a_ventas"],
])
def test_checkpoint_resume_keeps_tools_ids_and_handoffs(network, names):
    graph_module, _ = network
    calls = [dict(name=name, args=({"reason" if name == "transfer_to_sales" else "motivo": "Faltante confirmado"}
        if "sales" in name or "ventas" in name else {}), id="call-" + str(index)) for index, name in enumerate(names)]
    state = value()
    state.update(messages=[HumanMessage(content="Consultar SSD de prueba"), AIMessage(content="", tool_calls=calls)],
                 current_agent="compras", handoff_count=0, handoff_history=[], handoff_records=[])
    config = {"configurable": {"thread_id": "purchasing-tools-module"}}
    saver = MemorySaver()
    graph_module.build_graph(checkpointer=saver).update_state(config, state, as_node="compras")
    result = graph_module.build_graph(checkpointer=saver).invoke(None, config, interrupt_after=["auditar_compras"])
    outputs = [message for message in result["messages"] if isinstance(message, ToolMessage)]
    assert [(message.name, message.tool_call_id) for message in outputs] == [(call["name"], call["id"]) for call in calls]
    assert all(message.status != "error" for message in outputs)
    is_handoff = "sales" in names[0] or "ventas" in names[0]
    assert result["handoff_count"] == int(is_handoff)
    assert result["handoff_history"] == ([{"origin": "compras", "destination": "ventas"}] if is_handoff else [])
    assert not result.get("payment_id") and not result.get("quote_id")


def test_legacy_shim_and_canonical_ast_have_one_implementation():
    legacy = (ROOT / "app/agents/decentralized/tools/compras_tools.py").read_text(encoding="utf-8")
    assert '".purchasing_tools"' in legacy
    assert not any(isinstance(node, (ast.FunctionDef, ast.ClassDef)) for node in ast.parse(legacy).body)
    canonical = ast.parse((ROOT / "app/agents/decentralized/tools/purchasing_tools.py").read_text(encoding="utf-8"))
    assert {node.name for node in canonical.body if isinstance(node, ast.FunctionDef)} == {
        "consultar_fuentes_abastecimiento", "transferir_a_ventas"}
