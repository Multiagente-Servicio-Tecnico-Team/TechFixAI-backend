import importlib
import inspect
import json
from pathlib import Path
import subprocess
import sys
from types import ModuleType

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver

from test_compras import value
from test_software_e2e import network


LEGACY = "app.agents.decentralized.compras"
CANONICAL = "app.agents.decentralized.purchasing"
ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("first", ["compras", "purchasing"])
@pytest.mark.parametrize("style", ["importlib", "package"])
def test_fresh_process_import_orders_share_one_initialization(first, style):
    script = r'''
import importlib
import json
from pathlib import Path
import sys
sys.path.insert(0, sys.argv[1])
executions = []
def profile(frame, event, arg):
    if event == "call" and frame.f_code.co_name == "<module>" and Path(frame.f_code.co_filename).name == "purchasing.py":
        executions.append(frame.f_code.co_filename)
sys.setprofile(profile)
package = "app.agents.decentralized"
first = sys.argv[2]
second = "purchasing" if first == "compras" else "compras"
def load(name):
    if sys.argv[3] == "package":
        namespace = {}
        exec("from app.agents.decentralized import " + name, namespace)
        return namespace[name]
    return importlib.import_module(package + "." + name)
one, two = load(first), load(second)
sys.setprofile(None)
assert one is two
assert sys.modules[package + ".compras"] is sys.modules[package + ".purchasing"] is one
from app.agents.decentralized import compras, purchasing
assert compras is purchasing is one
assert importlib.import_module(package + ".purchasing") is one
assert importlib.import_module(package + ".compras") is one
assert one.purchasing_node is one.compras_node
assert one.purchasing_tools is one.compras_tools
assert len(executions) == 1
print(json.dumps({"initializations": len(executions), "name": one.__name__,
                  "spec": one.__spec__.name, "file": Path(one.__file__).name}))
'''
    result = subprocess.run([sys.executable, "-B", "-c", script, str(ROOT), first, style],
                            cwd=ROOT, capture_output=True, text=True, timeout=60, check=True)
    assert json.loads(result.stdout) == {"initializations": 1, "name": CANONICAL, "spec": CANONICAL, "file": "purchasing.py"}


def test_exports_metadata_and_graph_capture_remain_original(network):
    graph_module, _ = network
    from app.agents.decentralized import compras, purchasing
    assert compras is purchasing is importlib.import_module(CANONICAL) is importlib.import_module(LEGACY)
    assert purchasing.__name__ == purchasing.__spec__.name == CANONICAL
    assert Path(purchasing.__file__) == ROOT / "app/agents/decentralized/purchasing.py"
    assert inspect.getsourcefile(purchasing.purchasing_node) == purchasing.__file__
    assert purchasing.purchasing_node.__globals__ is purchasing.__dict__
    assert purchasing.purchasing_node.__module__ == CANONICAL
    assert inspect.getmodule(purchasing.purchasing_node) is purchasing
    assert "def purchasing_node(state: AgentState):" in inspect.getsource(purchasing.purchasing_node)
    assert "def purchasing_node(state: AgentState):" in inspect.getsource(purchasing)
    assert graph_module.purchasing_node is purchasing.purchasing_node is purchasing.compras_node
    assert graph_module.purchasing_tools is purchasing.purchasing_tools is purchasing.compras_tools


@pytest.mark.parametrize("path", [LEGACY, CANONICAL])
@pytest.mark.parametrize("attribute", ["purchasing_tools", "compras_tools", "purchasing_node", "compras_node"])
def test_reassignment_is_shared_and_monkeypatch_restores(network, monkeypatch, path, attribute):
    source = importlib.import_module(path)
    other = importlib.import_module(CANONICAL if path == LEGACY else LEGACY)
    original = getattr(source, attribute)
    replacement = [] if attribute.endswith("tools") else lambda state: {"current_agent": "compras"}
    with monkeypatch.context() as patch:
        patch.setattr(source, attribute, replacement)
        assert getattr(other, attribute) is replacement
    assert getattr(source, attribute) is getattr(other, attribute) is original


def test_shared_list_mutation_and_graph_capture_boundary(network):
    graph_module, _ = network
    legacy, canonical = importlib.import_module(LEGACY), importlib.import_module(CANONICAL)
    original = canonical.purchasing_tools
    previous = list(original)
    replacement = original[0].model_copy()
    try:
        original[:] = [replacement]
        assert legacy.compras_tools is original is graph_module.purchasing_tools
        tools = graph_module.build_graph().get_graph().nodes["compras_tools"].data.tools_by_name
        assert tools[replacement.name] is replacement
    finally:
        original[:] = previous


def test_coherent_sys_modules_fixture_and_graph_import(network, monkeypatch):
    from test_software_e2e import network as network_fixture
    original = importlib.import_module(LEGACY)
    replacement = ModuleType(LEGACY)
    replacement.purchasing_node = replacement.compras_node = original.purchasing_node
    replacement.purchasing_tools = replacement.compras_tools = original.purchasing_tools
    package = importlib.import_module("app.agents.decentralized")
    with monkeypatch.context() as patch:
        for path in (LEGACY, CANONICAL):
            patch.setitem(sys.modules, path, replacement)
        patch.setattr(package, "compras", replacement)
        patch.setattr(package, "purchasing", replacement)
        assert importlib.import_module(CANONICAL) is importlib.import_module(LEGACY) is replacement
        graph_module, _ = network_fixture.__wrapped__(patch)
        assert graph_module.purchasing_node is replacement.purchasing_node
        assert graph_module.purchasing_tools is replacement.purchasing_tools
    assert importlib.import_module(CANONICAL) is importlib.import_module(LEGACY) is original


@pytest.mark.parametrize("stock", [0, 3, 5])
def test_shared_node_preserves_functional_results_and_input(network, stock):
    from copy import deepcopy
    legacy, canonical = importlib.import_module(LEGACY), importlib.import_module(CANONICAL)
    state = value(stock=stock)
    before = deepcopy(state)
    one, two = legacy.compras_node(state), canonical.purchasing_node(state)
    def project(result):
        return {**result, "messages": [(message.content, [(call["name"], call["args"]) for call in message.tool_calls])
                                       for message in result["messages"]]}
    assert project(one) == project(two) and state == before
    assert inspect.signature(legacy.compras_node) == inspect.signature(canonical.purchasing_node)


@pytest.mark.parametrize("tool_name", ["transfer_to_sales", "transferir_a_ventas"])
def test_legacy_checkpoint_resumes_with_same_nodes_and_handoff(network, tool_name):
    graph_module, _ = network
    from app.agents.decentralized.purchasing import purchasing_node
    assert graph_module.AGENT_NODES["compras"] is purchasing_node
    event = AIMessage(content="", id="event", tool_calls=[dict(name=tool_name,
        args={"reason" if tool_name == "transfer_to_sales" else "motivo": "Evaluar faltantes"}, id="call")])
    state = value()
    state.update(messages=[HumanMessage(content="Consulta", id="human"), event], current_agent="compras",
                 handoff_count=0, handoff_history=[], handoff_records=[])
    saver = MemorySaver()
    config = {"configurable": {"thread_id": "purchasing-module"}}
    graph_module.build_graph(checkpointer=saver).update_state(config, state, as_node="compras")
    result = graph_module.build_graph(checkpointer=saver).invoke(None, config, interrupt_after=["auditar_compras"])
    outputs = [message for message in result["messages"] if isinstance(message, ToolMessage)]
    assert [(message.name, message.tool_call_id) for message in outputs] == [(tool_name, "call")]
    assert outputs[0].status != "error"
    assert result["handoff_history"] == [{"origin": "compras", "destination": "ventas"}]
    assert result["handoff_count"] == 1


@pytest.mark.parametrize("reload_path", [LEGACY, CANONICAL])
def test_reload_retains_module_aliases_but_recreates_python_exports_in_fresh_process(reload_path):
    script = r'''
import importlib
from pathlib import Path
import sys
sys.path.insert(0, sys.argv[1])
canonical_name = "app.agents.decentralized.purchasing"
legacy_name = "app.agents.decentralized.compras"
canonical = importlib.import_module(canonical_name)
legacy = importlib.import_module(legacy_name)
captured_node, captured_tools = canonical.purchasing_node, canonical.purchasing_tools
reloaded = importlib.reload(importlib.import_module(sys.argv[2]))
assert reloaded is canonical is legacy
assert importlib.import_module(canonical_name) is importlib.import_module(legacy_name) is reloaded
from app.agents.decentralized import compras, purchasing
assert compras is purchasing is reloaded
assert reloaded.__name__ == reloaded.__spec__.name == canonical_name
assert Path(reloaded.__file__).name == "purchasing.py"
assert reloaded.purchasing_node is reloaded.compras_node
assert reloaded.purchasing_tools is reloaded.compras_tools
assert captured_node is not reloaded.purchasing_node
assert captured_tools is not reloaded.purchasing_tools
assert captured_node.__globals__ is reloaded.purchasing_node.__globals__ is reloaded.__dict__
print("reload contract verified")
'''
    result = subprocess.run([sys.executable, "-B", "-c", script, str(ROOT), reload_path],
                            cwd=ROOT, capture_output=True, text=True, timeout=60, check=True)
    assert result.stdout.strip() == "reload contract verified"


def test_canonical_source_contains_implementation_and_legacy_source_only_aliases():
    import ast
    canonical = ROOT / "app/agents/decentralized/purchasing.py"
    legacy = ROOT / "app/agents/decentralized/compras.py"
    functions = lambda path: [node.name for node in ast.parse(path.read_text(encoding="utf-8")).body
                             if isinstance(node, ast.FunctionDef)]
    assert functions(canonical) == ["purchasing_node"]
    assert functions(legacy) == []
    assert '".purchasing"' in legacy.read_text(encoding="utf-8")
