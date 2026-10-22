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

from test_facturacion import fixture
from test_software_e2e import network


LEGACY = "app.agents.decentralized.facturacion"
CANONICAL = "app.agents.decentralized.billing"
ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("first", ["facturacion", "billing"])
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
    if event == "call" and frame.f_code.co_name == "<module>" and Path(frame.f_code.co_filename).name == "billing.py":
        executions.append(frame.f_code.co_filename)
sys.setprofile(profile)
package = "app.agents.decentralized"
first = sys.argv[2]
second = "billing" if first == "facturacion" else "facturacion"
def load(name):
    if sys.argv[3] == "package":
        namespace = {}
        exec("from app.agents.decentralized import " + name, namespace)
        return namespace[name]
    return importlib.import_module(package + "." + name)
one, two = load(first), load(second)
sys.setprofile(None)
assert one is two
assert sys.modules[package + ".facturacion"] is sys.modules[package + ".billing"] is one
from app.agents.decentralized import facturacion, billing
assert facturacion is billing is one
assert importlib.import_module(package + ".billing") is one
assert importlib.import_module(package + ".facturacion") is one
assert one.billing_node is one.facturacion_node
assert one.billing_tools is one.facturacion_tools
assert len(executions) == 1
print(json.dumps({"initializations": len(executions), "name": one.__name__,
                  "spec": one.__spec__.name, "file": Path(one.__file__).name}))
'''
    result = subprocess.run([sys.executable, "-B", "-c", script, str(ROOT), first, style],
                            cwd=ROOT, capture_output=True, text=True, timeout=60, check=True)
    assert json.loads(result.stdout) == {"initializations": 1, "name": CANONICAL, "spec": CANONICAL, "file": "billing.py"}


def test_exports_metadata_and_graph_capture_remain_original(network):
    graph_module, _ = network
    from app.agents.decentralized import facturacion, billing
    assert facturacion is billing is importlib.import_module(CANONICAL) is importlib.import_module(LEGACY)
    assert billing.__name__ == billing.__spec__.name == CANONICAL
    assert Path(billing.__file__) == ROOT / "app/agents/decentralized/billing.py"
    assert inspect.getsourcefile(billing.billing_node) == billing.__file__
    assert billing.billing_node.__globals__ is billing.__dict__
    assert billing.billing_node.__module__ == CANONICAL
    assert inspect.getmodule(billing.billing_node) is billing
    assert "def billing_node(state: AgentState," in inspect.getsource(billing.billing_node)
    assert "def billing_node(state: AgentState," in inspect.getsource(billing)
    assert graph_module.billing_node is billing.billing_node is billing.facturacion_node
    assert graph_module.billing_tools is billing.billing_tools is billing.facturacion_tools


@pytest.mark.parametrize("path", [LEGACY, CANONICAL])
@pytest.mark.parametrize("attribute", ["billing_tools", "facturacion_tools", "billing_node", "facturacion_node"])
def test_reassignment_is_shared_and_monkeypatch_restores(network, monkeypatch, path, attribute):
    source = importlib.import_module(path)
    other = importlib.import_module(CANONICAL if path == LEGACY else LEGACY)
    original = getattr(source, attribute)
    replacement = [] if attribute.endswith("tools") else lambda state: {"current_agent": "facturacion"}
    with monkeypatch.context() as patch:
        patch.setattr(source, attribute, replacement)
        assert getattr(other, attribute) is replacement
    assert getattr(source, attribute) is getattr(other, attribute) is original


def test_shared_list_mutation_and_graph_capture_boundary(network):
    graph_module, _ = network
    legacy, canonical = importlib.import_module(LEGACY), importlib.import_module(CANONICAL)
    original = canonical.billing_tools
    previous = list(original)
    replacement = original[0].model_copy()
    try:
        original[:] = [replacement]
        assert legacy.facturacion_tools is original is graph_module.billing_tools
        tools = graph_module.build_graph().get_graph().nodes["facturacion_tools"].data.tools_by_name
        assert tools[replacement.name] is replacement
    finally:
        original[:] = previous


def test_coherent_sys_modules_fixture_and_graph_import(network, monkeypatch):
    from test_software_e2e import network as network_fixture
    original = importlib.import_module(LEGACY)
    replacement = ModuleType(LEGACY)
    replacement.billing_node = replacement.facturacion_node = original.billing_node
    replacement.billing_tools = replacement.facturacion_tools = original.billing_tools
    package = importlib.import_module("app.agents.decentralized")
    with monkeypatch.context() as patch:
        for path in (LEGACY, CANONICAL):
            patch.setitem(sys.modules, path, replacement)
        patch.setattr(package, "facturacion", replacement)
        patch.setattr(package, "billing", replacement)
        assert importlib.import_module(CANONICAL) is importlib.import_module(LEGACY) is replacement
        graph_module, _ = network_fixture.__wrapped__(patch)
        assert graph_module.billing_node is replacement.billing_node
        assert graph_module.billing_tools is replacement.billing_tools
    assert importlib.import_module(CANONICAL) is importlib.import_module(LEGACY) is original


@pytest.mark.parametrize("authenticated", [True, False])
def test_shared_node_preserves_preparation_retry_and_no_writes(network, authenticated):
    from copy import deepcopy
    legacy, canonical = importlib.import_module(LEGACY), importlib.import_module(CANONICAL)
    state, repo = fixture()
    before = deepcopy(state)
    identity = 10 if authenticated else None
    one = legacy.facturacion_node(state, repository=repo, authenticated_customer_id=identity)
    retry_state = {**state, **one}
    two = canonical.billing_node(retry_state, repository=repo, authenticated_customer_id=identity)
    assert state == before
    if authenticated:
        assert one["pending_payment_operation"] == two["pending_payment_operation"]
    else:
        assert "pending_payment_operation" not in one and "pending_payment_operation" not in two
    assert "payment_id" not in one and "payment_code" not in one
    repo.create_pending_payment.assert_not_called()
    assert inspect.signature(legacy.facturacion_node) == inspect.signature(canonical.billing_node)


@pytest.mark.parametrize("tool_name", ["transfer_to_support", "transferir_a_soporte"])
def test_legacy_checkpoint_resumes_with_same_nodes_and_handoff(network, tool_name):
    graph_module, _ = network
    from app.agents.decentralized.billing import billing_node
    assert graph_module.AGENT_NODES["facturacion"] is billing_node
    event = AIMessage(content="", id="event", tool_calls=[dict(name=tool_name,
        args={"reason" if tool_name == "transfer_to_support" else "motivo": "Evaluar consulta"}, id="call")])
    state = dict(request_revision=2, customer_id=10)
    state.update(messages=[HumanMessage(content="Consulta", id="human"), event], current_agent="facturacion",
                 handoff_count=0, handoff_history=[], handoff_records=[])
    saver = MemorySaver()
    config = {"configurable": {"thread_id": "billing-module"}}
    graph_module.build_graph(checkpointer=saver).update_state(config, state, as_node="facturacion")
    result = graph_module.build_graph(checkpointer=saver).invoke(None, config, interrupt_after=["auditar_facturacion"])
    outputs = [message for message in result["messages"] if isinstance(message, ToolMessage)]
    assert [(message.name, message.tool_call_id) for message in outputs] == [(tool_name, "call")]
    assert outputs[0].status != "error"
    assert result["handoff_history"] == [{"origin": "facturacion", "destination": "soporte"}]
    assert result["handoff_count"] == 1


@pytest.mark.parametrize("reload_path", [LEGACY, CANONICAL])
def test_reload_retains_module_aliases_but_recreates_python_exports_in_fresh_process(reload_path):
    script = r'''
import importlib
from pathlib import Path
import sys
sys.path.insert(0, sys.argv[1])
canonical_name = "app.agents.decentralized.billing"
legacy_name = "app.agents.decentralized.facturacion"
canonical = importlib.import_module(canonical_name)
legacy = importlib.import_module(legacy_name)
captured_node, captured_tools = canonical.billing_node, canonical.billing_tools
reloaded = importlib.reload(importlib.import_module(sys.argv[2]))
assert reloaded is canonical is legacy
assert importlib.import_module(canonical_name) is importlib.import_module(legacy_name) is reloaded
from app.agents.decentralized import facturacion, billing
assert facturacion is billing is reloaded
assert reloaded.__name__ == reloaded.__spec__.name == canonical_name
assert Path(reloaded.__file__).name == "billing.py"
assert reloaded.billing_node is reloaded.facturacion_node
assert reloaded.billing_tools is reloaded.facturacion_tools
assert captured_node is not reloaded.billing_node
assert captured_tools is not reloaded.billing_tools
assert captured_node.__globals__ is reloaded.billing_node.__globals__ is reloaded.__dict__
print("reload contract verified")
'''
    result = subprocess.run([sys.executable, "-B", "-c", script, str(ROOT), reload_path],
                            cwd=ROOT, capture_output=True, text=True, timeout=60, check=True)
    assert result.stdout.strip() == "reload contract verified"


def test_canonical_source_contains_implementation_and_legacy_source_only_aliases():
    import ast
    canonical = ROOT / "app/agents/decentralized/billing.py"
    legacy = ROOT / "app/agents/decentralized/facturacion.py"
    functions = lambda path: [node.name for node in ast.parse(path.read_text(encoding="utf-8")).body
                             if isinstance(node, ast.FunctionDef)]
    assert functions(canonical) == ["billing_node"]
    assert functions(legacy) == []
    assert '".billing"' in legacy.read_text(encoding="utf-8")
