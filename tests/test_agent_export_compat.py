from copy import deepcopy
import importlib
import importlib.util
import inspect
from pathlib import Path
import sys
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver
from test_software_e2e import network, call

AGENTS = [("soporte","support"),("tecnico","hardware"),("ventas","sales"),("almacen","warehouse"),
          ("compras","purchasing"),("facturacion","billing"),("logistica","logistics"),("garantia","warranty")]


@pytest.mark.parametrize("role,canonical",AGENTS)
def test_english_and_legacy_entry_exports_share_object_signature_and_globals(network,role,canonical):
    graph_module,_=network
    module=importlib.import_module("app.agents.decentralized."+role)
    old,new=getattr(module,role+"_node"),getattr(module,canonical+"_node")
    assert old is new and new.__name__==canonical+"_node"
    assert inspect.signature(old)==inspect.signature(new)
    assert new.__globals__ is module.__dict__
    assert graph_module.AGENT_NODES[role] is new
    assert getattr(graph_module,role+"_node") is new
    assert getattr(graph_module,canonical+"_node") is new


@pytest.mark.parametrize("role,canonical",AGENTS)
def test_both_entry_points_return_equal_results_without_mutating_state(network,role,canonical):
    module=importlib.import_module("app.agents.decentralized."+role)
    state=dict(messages=[HumanMessage(content="Consulta general")],request_revision=2)
    before=deepcopy(state)
    assert getattr(module,role+"_node")(state)==getattr(module,canonical+"_node")(state)
    assert state==before


@pytest.mark.parametrize("role,canonical,attribute,text",[
    ("soporte","support","soporte_llm","Consulta general"),
    ("tecnico","hardware","tecnico_llm","Consulta general"),
    ("tecnico","hardware","tecnico_llm_rag","Consulta documentacion tecnica"),
    ("ventas","sales","ventas_llm","Consulta general"),
    ("almacen","warehouse","almacen_llm","Consulta general"),
])
def test_legacy_model_reassignment_is_seen_by_both_entry_points(network,monkeypatch,role,canonical,attribute,text):
    module=importlib.import_module("app.agents.decentralized."+role)
    response=call("request_inventory",query="fixture") if role=="ventas" else AIMessage(content="patched model")
    replacement=MagicMock();replacement.invoke.return_value=response
    monkeypatch.setattr(module,attribute,replacement)
    state=dict(messages=[HumanMessage(content=text)])
    first=getattr(module,canonical+"_node")(state)
    second=getattr(module,role+"_node")(state)
    assert replacement.invoke.call_count==2
    assert first["messages"][0] is response and second["messages"][0] is response


@pytest.mark.parametrize("role",[role for role,_ in AGENTS]+["software"])
def test_legacy_registry_and_dynamic_lookup_remain_usable(network,monkeypatch,role):
    graph_module,_=network
    module=importlib.import_module("app.agents.decentralized."+role)
    active=getattr(module,role+"_tools")
    assert getattr(graph_module,role+"_tools") is active
    assert len(active)==len({tool.name for tool in active})
    assert not any(tool.name.startswith("transferir_a_") for tool in active)
    replacement=list(active)
    monkeypatch.setattr(graph_module,role+"_tools",replacement)
    assert getattr(graph_module,role+"_tools") is replacement
    registered=graph_module.build_graph().get_graph().nodes[role+"_tools"].data.tools_by_name
    assert {tool.name for tool in replacement} <= set(registered)
    assert all(registered[tool.name] is tool for tool in replacement)


@pytest.mark.parametrize("role,canonical",AGENTS)
def test_loading_original_path_exports_both_names_without_duplicate_model_initialization(network,monkeypatch,role,canonical):
    groq=sys.modules["langchain_groq"]
    original=groq.ChatGroq
    created=[]
    class CountingGroq(original):
        def __init__(self,**kwargs):
            created.append(kwargs)
            super().__init__(**kwargs)
    monkeypatch.setattr(groq,"ChatGroq",CountingGroq)
    path=Path(__file__).resolve().parents[1]/f"app/agents/decentralized/{role}.py"
    spec=importlib.util.spec_from_file_location("isolated_export_"+role,path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert getattr(module,role+"_node") is getattr(module,canonical+"_node")
    assert len(created)==(1 if role in {"soporte","tecnico","ventas","almacen"} else 0)


def test_legacy_hardware_checkpoint_resumes_with_new_entry_function(network):
    module,_=network
    saver=MemorySaver();config={"configurable":{"thread_id":"entry-compat"}}
    event=call("transferir_a_tecnico",motivo="Evaluar");event.id="event"
    state=dict(messages=[HumanMessage(content="Consulta general"),event],current_agent="soporte",handoff_history=[],handoff_count=0,handoff_records=[],customer_id=1,ticket_id=7)
    graph=module.build_graph(checkpointer=saver)
    graph.update_state(config,state,as_node="soporte")
    assert graph.get_state(config).next==("soporte_tools",)
    result=module.build_graph(checkpointer=saver).invoke(None,config)
    outputs=[m for m in result["messages"] if isinstance(m,ToolMessage)]
    assert len(outputs)==1 and outputs[0].name=="transferir_a_tecnico" and outputs[0].tool_call_id==event.tool_calls[0]["id"]
    assert result["current_agent"]=="tecnico" and result["ticket_id"]==7 and result["customer_id"]==1
    assert result["handoff_history"]==[{"origin":"soporte","destination":"tecnico"}]
