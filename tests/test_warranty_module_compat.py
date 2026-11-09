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

from test_software_e2e import network


LEGACY = "app.agents.decentralized.garantia"
CANONICAL = "app.agents.decentralized.warranty"
ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("first", ["garantia", "warranty"])
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
    if event == "call" and frame.f_code.co_name == "<module>" and Path(frame.f_code.co_filename).name == "warranty.py":
        executions.append(frame.f_code.co_filename)
sys.setprofile(profile)
package = "app.agents.decentralized"
first = sys.argv[2]
second = "warranty" if first == "garantia" else "garantia"
def load(name):
    if sys.argv[3] == "package":
        namespace = {}
        exec("from app.agents.decentralized import " + name, namespace)
        return namespace[name]
    return importlib.import_module(package + "." + name)
one, two = load(first), load(second)
sys.setprofile(None)
assert one is two
assert sys.modules[package + ".garantia"] is sys.modules[package + ".warranty"] is one
from app.agents.decentralized import garantia, warranty
assert garantia is warranty is one
assert importlib.import_module(package + ".warranty") is one
assert importlib.import_module(package + ".garantia") is one
assert one.warranty_node is one.garantia_node
assert one.warranty_tools is one.garantia_tools
assert len(executions) == 1
print(json.dumps({"initializations": len(executions), "name": one.__name__,
                  "spec": one.__spec__.name, "file": Path(one.__file__).name}))
'''
    result = subprocess.run([sys.executable, "-B", "-c", script, str(ROOT), first, style],
                            cwd=ROOT, capture_output=True, text=True, timeout=60, check=True)
    assert json.loads(result.stdout) == {"initializations": 1, "name": CANONICAL, "spec": CANONICAL, "file": "warranty.py"}


def test_exports_metadata_and_graph_capture_remain_original(network):
    graph_module, _ = network
    from app.agents.decentralized import garantia, warranty
    assert garantia is warranty is importlib.import_module(CANONICAL) is importlib.import_module(LEGACY)
    assert warranty.__name__ == warranty.__spec__.name == CANONICAL
    assert Path(warranty.__file__) == ROOT / "app/agents/decentralized/warranty.py"
    assert inspect.getsourcefile(warranty.warranty_node) == warranty.__file__
    assert warranty.warranty_node.__globals__ is warranty.__dict__
    assert warranty.warranty_node.__module__ == CANONICAL
    assert inspect.getmodule(warranty.warranty_node) is warranty
    assert "def warranty_node(state," in inspect.getsource(warranty.warranty_node)
    assert "def warranty_node(state," in inspect.getsource(warranty)
    assert graph_module.warranty_node is warranty.warranty_node is warranty.garantia_node
    assert graph_module.warranty_tools is warranty.warranty_tools is warranty.garantia_tools
    source = importlib.import_module("app.agents.decentralized.tools.warranty_handoff_tools")
    assert warranty.warranty_tools is source.warranty_handoff_tools


@pytest.mark.parametrize("path", [LEGACY, CANONICAL])
@pytest.mark.parametrize("attribute", ["warranty_tools", "garantia_tools", "warranty_node", "garantia_node"])
def test_reassignment_is_shared_and_monkeypatch_restores(network, monkeypatch, path, attribute):
    source = importlib.import_module(path)
    other = importlib.import_module(CANONICAL if path == LEGACY else LEGACY)
    original = getattr(source, attribute)
    replacement = [] if attribute.endswith("tools") else lambda state: {"current_agent": "garantia"}
    with monkeypatch.context() as patch:
        patch.setattr(source, attribute, replacement)
        assert getattr(other, attribute) is replacement
    assert getattr(source, attribute) is getattr(other, attribute) is original


def test_shared_list_mutation_and_graph_capture_boundary(network):
    graph_module, _ = network
    legacy, canonical = importlib.import_module(LEGACY), importlib.import_module(CANONICAL)
    original = canonical.warranty_tools
    previous = list(original)
    replacement = original[0].model_copy()
    try:
        original[:] = [replacement]
        assert legacy.garantia_tools is original is graph_module.warranty_tools
        tools = graph_module.build_graph().get_graph().nodes["garantia_tools"].data.tools_by_name
        assert tools[replacement.name] is replacement
    finally:
        original[:] = previous


def test_coherent_sys_modules_fixture_and_graph_import(network, monkeypatch):
    from test_software_e2e import network as network_fixture
    original = importlib.import_module(LEGACY)
    replacement = ModuleType(LEGACY)
    replacement.warranty_node = replacement.garantia_node = original.warranty_node
    replacement.warranty_tools = replacement.garantia_tools = original.warranty_tools
    package = importlib.import_module("app.agents.decentralized")
    with monkeypatch.context() as patch:
        for path in (LEGACY, CANONICAL):
            patch.setitem(sys.modules, path, replacement)
        patch.setattr(package, "garantia", replacement)
        patch.setattr(package, "warranty", replacement)
        assert importlib.import_module(CANONICAL) is importlib.import_module(LEGACY) is replacement
        graph_module, _ = network_fixture.__wrapped__(patch)
        assert graph_module.warranty_node is replacement.warranty_node
        assert graph_module.warranty_tools is replacement.warranty_tools
    assert importlib.import_module(CANONICAL) is importlib.import_module(LEGACY) is original


def warranty_fixture():
    from unittest.mock import MagicMock
    repo = MagicMock()
    repo.get_warranty.return_value = dict(id=2, warranty_code="WAR-TEST", status="ACTIVE",
        effective_status="ACTIVE", start_date="2026-01-01", end_date="2026-12-31",
        warranty_months=12, item_or_service_name="Fixture")
    repo.get_ticket.return_value = dict(request_type="WARRANTY_CLAIM", status="NEW", failure_description="No enciende")
    state = dict(customer_id=10, ticket_id=1, request_revision=0, messages=[], warranty_code="WAR-TEST")
    return state, repo


@pytest.mark.parametrize("mode", ["query", "claim", "unauthenticated"])
def test_shared_node_preserves_results_retry_and_no_writes(network, mode):
    from copy import deepcopy
    from unittest.mock import call
    legacy, canonical = importlib.import_module(LEGACY), importlib.import_module(CANONICAL)
    state, repo = warranty_fixture()
    state["intent"] = "WARRANTY_CLAIM" if mode == "claim" else "WARRANTY_STATUS_CHECK"
    before = deepcopy(state)
    identity = None if mode == "unauthenticated" else 10
    one = legacy.garantia_node(state, repository=repo, authenticated_customer_id=identity)
    two = canonical.warranty_node({**state, **one}, repository=repo, authenticated_customer_id=identity)
    assert state == before
    if mode == "claim":
        assert one["pending_warranty_operation"] == two["pending_warranty_operation"]
        assert repo.mock_calls == [call.get_warranty(customer_id=10, warranty_code="WAR-TEST"),
                                   call.get_ticket(customer_id=10, ticket_id=1)] * 2
    elif mode == "query":
        assert one == two and "pending_warranty_operation" not in one
        assert repo.mock_calls == [call.get_warranty(customer_id=10, warranty_code="WAR-TEST")] * 2
    else:
        assert one == two and repo.mock_calls == []
    assert "warranty_claim_id" not in one
    assert inspect.signature(legacy.garantia_node) == inspect.signature(canonical.warranty_node)


@pytest.mark.parametrize("failure", [LookupError, ValueError, RuntimeError])
def test_repository_errors_preserve_results_without_writes(network, failure):
    legacy, canonical = importlib.import_module(LEGACY), importlib.import_module(CANONICAL)
    state, repo = warranty_fixture()
    repo.get_warranty.side_effect = failure("private details")
    one = legacy.garantia_node(state, repository=repo, authenticated_customer_id=10)
    two = canonical.warranty_node(state, repository=repo, authenticated_customer_id=10)
    assert one == two and not one["warranty_preparation_ready"]
    assert "private details" not in one["messages"][0].content
    assert all(call[0] == "get_warranty" for call in repo.mock_calls)


@pytest.mark.parametrize("path", [LEGACY, CANONICAL])
def test_graph_preserves_repository_and_authenticated_context(network, monkeypatch, path):
    from unittest.mock import MagicMock
    graph_module, _ = network
    state, repo = warranty_fixture()
    agent = importlib.import_module(path)
    assert agent.warranty_node is graph_module.warranty_node
    probe = MagicMock(return_value={"current_agent": "garantia", "messages": [AIMessage(content="Fixture response")]})
    monkeypatch.setattr(graph_module, "warranty_node", probe)
    graph = graph_module.build_graph(checkpointer=MemorySaver(), financial_repository=repo)
    graph.invoke({**state, "current_agent": "garantia"},
        {"configurable": {"thread_id": "warranty-injection"}}, context={"authenticated_customer_id": 10})
    probe.assert_called_once()
    assert probe.call_args.kwargs == {"repository": repo, "authenticated_customer_id": 10}
    assert repo.mock_calls == []


@pytest.mark.parametrize("tool_name", ["transfer_to_support", "transferir_a_soporte"])
def test_legacy_checkpoint_resumes_with_same_nodes_and_handoff(network, tool_name):
    graph_module, _ = network
    from app.agents.decentralized.warranty import warranty_node
    assert graph_module.AGENT_NODES["garantia"] is warranty_node
    event = AIMessage(content="", id="event", tool_calls=[dict(name=tool_name,
        args={"reason" if tool_name == "transfer_to_support" else "motivo": "Evaluar consulta"}, id="call")])
    state = dict(request_revision=2, customer_id=10)
    state.update(messages=[HumanMessage(content="Consulta", id="human"), event], current_agent="garantia",
                 handoff_count=0, handoff_history=[], handoff_records=[])
    saver = MemorySaver()
    config = {"configurable": {"thread_id": "warranty-module"}}
    graph_module.build_graph(checkpointer=saver).update_state(config, state, as_node="garantia")
    result = graph_module.build_graph(checkpointer=saver).invoke(None, config, interrupt_after=["auditar_garantia"])
    outputs = [message for message in result["messages"] if isinstance(message, ToolMessage)]
    assert [(message.name, message.tool_call_id) for message in outputs] == [(tool_name, "call")]
    assert outputs[0].status != "error"
    assert result["handoff_history"] == [{"origin": "garantia", "destination": "soporte"}]
    assert result["handoff_count"] == 1


@pytest.mark.parametrize("reload_path", [LEGACY, CANONICAL])
def test_reload_retains_module_aliases_but_recreates_python_exports_in_fresh_process(reload_path):
    script = r'''
import importlib
from pathlib import Path
import sys
sys.path.insert(0, sys.argv[1])
canonical_name = "app.agents.decentralized.warranty"
legacy_name = "app.agents.decentralized.garantia"
canonical = importlib.import_module(canonical_name)
legacy = importlib.import_module(legacy_name)
captured_node, captured_tools = canonical.warranty_node, canonical.warranty_tools
reloaded = importlib.reload(importlib.import_module(sys.argv[2]))
assert reloaded is canonical is legacy
assert importlib.import_module(canonical_name) is importlib.import_module(legacy_name) is reloaded
from app.agents.decentralized import garantia, warranty
assert garantia is warranty is reloaded
assert reloaded.__name__ == reloaded.__spec__.name == canonical_name
assert Path(reloaded.__file__).name == "warranty.py"
assert reloaded.warranty_node is reloaded.garantia_node
assert reloaded.warranty_tools is reloaded.garantia_tools
assert captured_node is not reloaded.warranty_node
assert captured_tools is reloaded.warranty_tools
source = importlib.import_module("app.agents.decentralized.tools.warranty_handoff_tools")
assert reloaded.warranty_tools is source.warranty_handoff_tools
assert captured_node.__globals__ is reloaded.warranty_node.__globals__ is reloaded.__dict__
print("reload contract verified")
'''
    result = subprocess.run([sys.executable, "-B", "-c", script, str(ROOT), reload_path],
                            cwd=ROOT, capture_output=True, text=True, timeout=60, check=True)
    assert result.stdout.strip() == "reload contract verified"


def test_canonical_source_contains_implementation_and_legacy_source_only_aliases():
    import ast
    canonical = ROOT / "app/agents/decentralized/warranty.py"
    legacy = ROOT / "app/agents/decentralized/garantia.py"
    functions = lambda path: [node.name for node in ast.parse(path.read_text(encoding="utf-8")).body
                             if isinstance(node, ast.FunctionDef)]
    assert functions(canonical) == ["warranty_node"]
    assert functions(legacy) == []
    assert '".warranty"' in legacy.read_text(encoding="utf-8")
