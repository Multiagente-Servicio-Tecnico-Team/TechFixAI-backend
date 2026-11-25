from copy import deepcopy
import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver
from pydantic import ValidationError
from app.agents.decentralized.tools import billing_handoff_tools as billing, logistics_handoff_tools as logistics, warranty_handoff_tools as warranty
from test_software_e2e import network

GROUPS = [("facturacion",billing,"support","soporte"),("facturacion",billing,"sales","ventas"),
          ("facturacion",billing,"logistics","logistica"),("logistica",logistics,"support","soporte"),
          ("garantia",warranty,"support","soporte"),("garantia",warranty,"logistics","logistica")]


def variants(module,target,destination):
    return getattr(module,"transfer_to_"+target),next(t for t in module.legacy_handoff_tools if t.name=="transferir_a_"+destination)


@pytest.mark.parametrize("role,module,target,destination",GROUPS)
def test_exact_schemas_and_equivalent_results(role,module,target,destination):
    new,old=variants(module,target,destination)
    for tool,key,wrong in [(new,"reason","motivo"),(old,"motivo","reason")]:
        schema=tool.tool_call_schema.model_json_schema()
        assert set(schema["properties"])==set(schema["required"])=={key}
        with pytest.raises(ValidationError):tool.invoke({wrong:"Evaluar"})
    assert new.invoke({"reason":"  Evaluar  "})==old.invoke({"motivo":"  Evaluar  "})


@pytest.mark.parametrize("role,module,target,destination",GROUPS)
@pytest.mark.parametrize("reason",["", "  ", None])
def test_local_invalid_reason_validation_preserved(role,module,target,destination,reason):
    new,old=variants(module,target,destination)
    for tool,key in [(new,"reason"),(old,"motivo")]:
        with pytest.raises((ValueError,ValidationError)):tool.invoke({key:reason})


@pytest.mark.parametrize("role,module",[("facturacion",billing),("logistica",logistics),("garantia",warranty)])
def test_active_and_legacy_registries_are_exact(network,role,module):
    graph_module,_=network
    names=[t.name for t in getattr(graph_module,role+"_tools")]
    expected={"transfer_to_"+target for origin,_,target,_ in GROUPS if origin==role}
    assert {n for n in names if n.startswith("transfer_to_")}==expected
    assert not any(n.startswith("transferir_") for n in names)
    assert len(names)==len(set(names))
    registered=graph_module.build_graph().get_graph().nodes[role+"_tools"].data.tools_by_name
    assert set(registered)==set(names)|{t.name for t in module.legacy_handoff_tools}|({"consultar_capacidades_financieras"} if role=="facturacion" else set())


@pytest.mark.parametrize("role,module,target,destination",GROUPS)
@pytest.mark.parametrize("legacy",[False,True])
def test_checkpoint_resolves_both_variants_with_same_audit(network,role,module,target,destination,legacy):
    graph_module,_=network
    new,old=variants(module,target,destination)
    name=(old if legacy else new).name
    event=AIMessage(content="",id="event",tool_calls=[dict(name=name,args={"motivo" if legacy else "reason":"Evaluar"},id="handoff")])
    before=deepcopy(event)
    saver=MemorySaver();config={"configurable":{"thread_id":"financial-handoff"}}
    graph_module.build_graph(checkpointer=saver).update_state(config,dict(messages=[HumanMessage(content="Consulta"),event],current_agent=role,handoff_count=0,handoff_history=[],handoff_records=[]),as_node=role)
    result=graph_module.build_graph(checkpointer=saver).invoke(None,config,interrupt_after=["auditar_"+role])
    outputs=[m for m in result["messages"] if isinstance(m,ToolMessage)]
    assert len(outputs)==1 and outputs[0].name==name and outputs[0].tool_call_id=="handoff" and outputs[0].status!="error"
    assert result["handoff_history"]==[{"origin":role,"destination":destination}]
    assert result["handoff_count"]==1 and result["handoff_records"][0]["reason"]=="Evaluar"
    assert event==before
    assert not any(result.get(k) for k in ["payment_id","logistics_record_id","warranty_claim_id"])


@pytest.mark.parametrize("role,module",[("facturacion",billing),("logistica",logistics),("garantia",warranty)])
@pytest.mark.parametrize("legacy_first",[False,True])
def test_mixed_batch_selects_first_successful_without_rewriting(network,role,module,legacy_first):
    graph_module,_=network
    routes=[(target,dest) for origin,_,target,dest in GROUPS if origin==role]
    selected=[routes[0],routes[-1]]
    calls=[]
    for index,((target,destination),legacy) in enumerate(zip(selected,[legacy_first,not legacy_first])):
        new,old=variants(module,target,destination)
        calls.append(dict(name=(old if legacy else new).name,args={"motivo" if legacy else "reason":"Evaluar"},id=str(index)))
    event=AIMessage(content="",id="batch",tool_calls=calls);before=deepcopy(event)
    saver=MemorySaver();config={"configurable":{"thread_id":"mixed"}}
    graph_module.build_graph(checkpointer=saver).update_state(config,dict(messages=[HumanMessage(content="Consulta"),event],current_agent=role,handoff_count=0,handoff_history=[],handoff_records=[]),as_node=role)
    result=graph_module.build_graph(checkpointer=saver).invoke(None,config,interrupt_after=["auditar_"+role])
    outputs=[m for m in result["messages"] if isinstance(m,ToolMessage)]
    assert [(m.name,m.tool_call_id) for m in outputs]==[(c["name"],c["id"]) for c in calls]
    assert all(m.status!="error" for m in outputs)
    assert result["handoff_history"]==[{"origin":role,"destination":selected[0][1]}]
    assert result["handoff_count"]==1 and event==before


@pytest.mark.parametrize("progress",[False,True])
def test_financial_cycles_and_legitimate_tool_progress(network,monkeypatch,progress):
    from test_software_e2e import call
    graph_module,controls=network
    def finance(state):
        messages=state["messages"]
        if progress and isinstance(messages[-1],ToolMessage) and messages[-1].name!="get_financial_capabilities":
            return {"current_agent":"facturacion","messages":[call("get_financial_capabilities")]}
        return {"current_agent":"facturacion","messages":[call("transfer_to_support",reason="Evaluar")]}
    monkeypatch.setitem(graph_module.AGENT_NODES,"facturacion",finance)
    monkeypatch.setitem(graph_module.AGENT_NODES,"soporte",lambda state: {"current_agent":"soporte","messages":[call("transfer_to_billing",reason="Evaluar")]})
    result=graph_module.build_graph().invoke(dict(messages=[HumanMessage(content="Consulta")],current_agent="facturacion"))
    assert result["next_agent"]=="finalizar" and result.get("errors")
    assert result["handoff_count"]>(2 if progress else 1)
    assert any("repetida" in e for e in result["errors"])
