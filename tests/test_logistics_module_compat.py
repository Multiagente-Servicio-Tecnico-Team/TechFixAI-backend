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

from test_logistica import setup
from test_software_e2e import network


LEGACY = "app.agents.decentralized.logistica"
CANONICAL = "app.agents.decentralized.logistics"
ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("first", ["logistica", "logistics"])
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
    if event == "call" and frame.f_code.co_name == "<module>" and Path(frame.f_code.co_filename).name == "logistics.py":
        executions.append(frame.f_code.co_filename)
sys.setprofile(profile)
package = "app.agents.decentralized"
first = sys.argv[2]
second = "logistics" if first == "logistica" else "logistica"
def load(name):
    if sys.argv[3] == "package":
        namespace = {}
        exec("from app.agents.decentralized import " + name, namespace)
        return namespace[name]
    return importlib.import_module(package + "." + name)
one, two = load(first), load(second)
sys.setprofile(None)
assert one is two
assert sys.modules[package + ".logistica"] is sys.modules[package + ".logistics"] is one
from app.agents.decentralized import logistica, logistics
assert logistica is logistics is one
assert importlib.import_module(package + ".logistics") is one
assert importlib.import_module(package + ".logistica") is one
assert one.logistics_node is one.logistica_node
assert one.logistics_tools is one.logistica_tools
assert len(executions) == 1
print(json.dumps({"initializations": len(executions), "name": one.__name__,
                  "spec": one.__spec__.name, "file": Path(one.__file__).name}))
'''
    result = subprocess.run([sys.executable, "-B", "-c", script, str(ROOT), first, style],
                            cwd=ROOT, capture_output=True, text=True, timeout=60, check=True)
    assert json.loads(result.stdout) == {"initializations": 1, "name": CANONICAL, "spec": CANONICAL, "file": "logistics.py"}


def test_exports_metadata_and_graph_capture_remain_original(network):
    graph_module, _ = network
    from app.agents.decentralized import logistica, logistics
    assert logistica is logistics is importlib.import_module(CANONICAL) is importlib.import_module(LEGACY)
    assert logistics.__name__ == logistics.__spec__.name == CANONICAL
    assert Path(logistics.__file__) == ROOT / "app/agents/decentralized/logistics.py"
    assert inspect.getsourcefile(logistics.logistics_node) == logistics.__file__
    assert logistics.logistics_node.__globals__ is logistics.__dict__
    assert logistics.logistics_node.__module__ == CANONICAL
    assert inspect.getmodule(logistics.logistics_node) is logistics
    assert "def logistics_node(state: AgentState," in inspect.getsource(logistics.logistics_node)
    assert "def logistics_node(state: AgentState," in inspect.getsource(logistics)
    assert graph_module.logistics_node is logistics.logistics_node is logistics.logistica_node
    assert graph_module.logistics_tools is logistics.logistics_tools is logistics.logistica_tools


@pytest.mark.parametrize("path", [LEGACY, CANONICAL])
@pytest.mark.parametrize("attribute", ["logistics_tools", "logistica_tools", "logistics_node", "logistica_node"])
def test_reassignment_is_shared_and_monkeypatch_restores(network, monkeypatch, path, attribute):
    source = importlib.import_module(path)
    other = importlib.import_module(CANONICAL if path == LEGACY else LEGACY)
    original = getattr(source, attribute)
    replacement = [] if attribute.endswith("tools") else lambda state: {"current_agent": "logistica"}
    with monkeypatch.context() as patch:
        patch.setattr(source, attribute, replacement)
        assert getattr(other, attribute) is replacement
    assert getattr(source, attribute) is getattr(other, attribute) is original


def test_shared_list_mutation_and_graph_capture_boundary(network):
    graph_module, _ = network
    legacy, canonical = importlib.import_module(LEGACY), importlib.import_module(CANONICAL)
    original = canonical.logistics_tools
    previous = list(original)
    replacement = original[0].model_copy()
    try:
        original[:] = [replacement]
        assert legacy.logistica_tools is original is graph_module.logistics_tools
        tools = graph_module.build_graph().get_graph().nodes["logistica_tools"].data.tools_by_name
        assert tools[replacement.name] is replacement
    finally:
        original[:] = previous


def test_coherent_sys_modules_fixture_and_graph_import(network, monkeypatch):
    from test_software_e2e import network as network_fixture
    original = importlib.import_module(LEGACY)
    replacement = ModuleType(LEGACY)
    replacement.logistics_node = replacement.logistica_node = original.logistics_node
    replacement.logistics_tools = replacement.logistica_tools = original.logistics_tools
    package = importlib.import_module("app.agents.decentralized")
    with monkeypatch.context() as patch:
        for path in (LEGACY, CANONICAL):
            patch.setitem(sys.modules, path, replacement)
        patch.setattr(package, "logistica", replacement)
        patch.setattr(package, "logistics", replacement)
        assert importlib.import_module(CANONICAL) is importlib.import_module(LEGACY) is replacement
        graph_module, _ = network_fixture.__wrapped__(patch)
        assert graph_module.logistics_node is replacement.logistics_node
        assert graph_module.logistics_tools is replacement.logistics_tools
    assert importlib.import_module(CANONICAL) is importlib.import_module(LEGACY) is original


@pytest.mark.parametrize("authenticated", [True, False])
def test_shared_node_preserves_preparation_retry_and_no_writes(network, authenticated):
    from copy import deepcopy
    from unittest.mock import call
    legacy, canonical = importlib.import_module(LEGACY), importlib.import_module(CANONICAL)
    repo, state = setup(text="Prefiero retiro presencial")
    before = deepcopy(state)
    identity = 10 if authenticated else None
    one = legacy.logistica_node(state, repository=repo, authenticated_customer_id=identity)
    two = canonical.logistics_node({**state, **one}, repository=repo, authenticated_customer_id=identity)
    assert state == before
    if authenticated:
        assert one["pending_logistics_operation"] == two["pending_logistics_operation"]
        assert repo.mock_calls == [call.get_logistics_context(customer_id=10, ticket_id=1)] * 2
    else:
        assert "pending_logistics_operation" not in one and "pending_logistics_operation" not in two
        assert repo.mock_calls == []
    assert inspect.signature(legacy.logistica_node) == inspect.signature(canonical.logistics_node)


@pytest.mark.parametrize("failure", [LookupError, ValueError, RuntimeError])
def test_repository_errors_preserve_results_without_writes(network, failure):
    legacy, canonical = importlib.import_module(LEGACY), importlib.import_module(CANONICAL)
    repo, state = setup(text="Prefiero retiro presencial")
    repo.get_logistics_context.side_effect = failure("private details")
    one = legacy.logistica_node(state, repository=repo, authenticated_customer_id=10)
    two = canonical.logistics_node(state, repository=repo, authenticated_customer_id=10)
    assert one == two and not one["logistics_preparation_ready"]
    assert "private details" not in one["messages"][0].content
    assert all(call[0] == "get_logistics_context" for call in repo.mock_calls)


@pytest.mark.parametrize("path", [LEGACY, CANONICAL])
def test_graph_injects_trusted_repository_and_identity(network, monkeypatch, path):
    from unittest.mock import MagicMock
    graph_module, _ = network
    agent = importlib.import_module(path)
    repo, state = setup(text="Prefiero retiro presencial")
    probe = MagicMock(return_value={"current_agent": "logistica"})
    monkeypatch.setattr(agent, "collect_logistics", lambda state: {"mode": "PHYSICAL_STORE"})
    original = agent.logistics_node
    result = original(state, repository=repo, authenticated_customer_id=10)
    assert result["pending_logistics_operation"]["payload"]["mode"] == "PHYSICAL_STORE"
    monkeypatch.setattr(graph_module, "logistics_node", probe)
    graph = graph_module.build_graph(checkpointer=MemorySaver(), financial_repository=repo)
    context = {"authenticated_customer_id": 10}
    graph.invoke({**state, "current_agent": "logistica"},
                 {"configurable": {"thread_id": "logistics-injection"}}, context=context)
    probe.assert_called_once()
    assert probe.call_args.kwargs == {"repository": repo, "authenticated_customer_id": 10}
    assert probe.call_args.args[0]["customer_id"] == 10
    repo.create_initial_logistics.assert_not_called()


@pytest.mark.parametrize("tool_name", ["transfer_to_support", "transferir_a_soporte"])
def test_legacy_checkpoint_resumes_with_same_nodes_and_handoff(network, tool_name):
    graph_module, _ = network
    from app.agents.decentralized.logistics import logistics_node
    assert graph_module.AGENT_NODES["logistica"] is logistics_node
    event = AIMessage(content="", id="event", tool_calls=[dict(name=tool_name,
        args={"reason" if tool_name == "transfer_to_support" else "motivo": "Evaluar consulta"}, id="call")])
    state = dict(request_revision=2, customer_id=10)
    state.update(messages=[HumanMessage(content="Consulta", id="human"), event], current_agent="logistica",
                 handoff_count=0, handoff_history=[], handoff_records=[])
    saver = MemorySaver()
    config = {"configurable": {"thread_id": "logistics-module"}}
    graph_module.build_graph(checkpointer=saver).update_state(config, state, as_node="logistica")
    result = graph_module.build_graph(checkpointer=saver).invoke(None, config, interrupt_after=["auditar_logistica"])
    outputs = [message for message in result["messages"] if isinstance(message, ToolMessage)]
    assert [(message.name, message.tool_call_id) for message in outputs] == [(tool_name, "call")]
    assert outputs[0].status != "error"
    assert result["handoff_history"] == [{"origin": "logistica", "destination": "soporte"}]
    assert result["handoff_count"] == 1


@pytest.mark.parametrize("reload_path", [LEGACY, CANONICAL])
def test_reload_retains_module_aliases_but_recreates_python_exports_in_fresh_process(reload_path):
    script = r'''
import importlib
from pathlib import Path
import sys
sys.path.insert(0, sys.argv[1])
canonical_name = "app.agents.decentralized.logistics"
legacy_name = "app.agents.decentralized.logistica"
canonical = importlib.import_module(canonical_name)
legacy = importlib.import_module(legacy_name)
captured_node, captured_tools = canonical.logistics_node, canonical.logistics_tools
reloaded = importlib.reload(importlib.import_module(sys.argv[2]))
assert reloaded is canonical is legacy
assert importlib.import_module(canonical_name) is importlib.import_module(legacy_name) is reloaded
from app.agents.decentralized import logistica, logistics
assert logistica is logistics is reloaded
assert reloaded.__name__ == reloaded.__spec__.name == canonical_name
assert Path(reloaded.__file__).name == "logistics.py"
assert reloaded.logistics_node is reloaded.logistica_node
assert reloaded.logistics_tools is reloaded.logistica_tools
assert captured_node is not reloaded.logistics_node
assert captured_tools is not reloaded.logistics_tools
assert captured_node.__globals__ is reloaded.logistics_node.__globals__ is reloaded.__dict__
print("reload contract verified")
'''
    result = subprocess.run([sys.executable, "-B", "-c", script, str(ROOT), reload_path],
                            cwd=ROOT, capture_output=True, text=True, timeout=60, check=True)
    assert result.stdout.strip() == "reload contract verified"


def test_canonical_source_contains_implementation_and_legacy_source_only_aliases():
    import ast
    canonical = ROOT / "app/agents/decentralized/logistics.py"
    legacy = ROOT / "app/agents/decentralized/logistica.py"
    functions = lambda path: [node.name for node in ast.parse(path.read_text(encoding="utf-8")).body
                             if isinstance(node, ast.FunctionDef)]
    assert functions(canonical) == ["collect_logistics", "logistics_node"]
    assert functions(legacy) == []
    assert '".logistics"' in legacy.read_text(encoding="utf-8")
