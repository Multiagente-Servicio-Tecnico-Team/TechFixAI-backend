from copy import deepcopy
import ast
from pathlib import Path
import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver
from pydantic import ValidationError
from app.agents.decentralized.tools import sales_handoff_tools as sales
from test_software_e2e import network, call

GROUPS=[("support","soporte"),("hardware","tecnico"),("billing","facturacion")]


def variants(target,destination):
    return getattr(sales,"transfer_to_"+target),next(t for t in sales.legacy_handoff_tools if t.name=="transferir_a_"+destination)


@pytest.mark.parametrize("target,destination",GROUPS)
def test_exact_schemas_and_hidden_legacy_arguments(target,destination):
    new,old=variants(target,destination)
    for tool,key,wrong in [(new,"reason","motivo"),(old,"motivo","reason")]:
        schema=tool.tool_call_schema.model_json_schema()
        assert set(schema["properties"])==set(schema["required"])=={key}
        assert schema["properties"][key]["type"]=="string"
        for arguments in [{wrong:"Evaluar"},{key:None},{}]:
            with pytest.raises(ValidationError):tool.invoke(arguments)


@pytest.mark.parametrize("target,destination",GROUPS)
@pytest.mark.parametrize("reason",["Evaluar","  Revisar  ","","  "])
def test_wrappers_preserve_local_results_and_validation(target,destination,reason):
    new,old=variants(target,destination)
    if target=="billing" and not reason.strip():
        for tool,key in [(new,"reason"),(old,"motivo")]:
            with pytest.raises(ValueError):tool.invoke({key:reason})
    else:
        assert new.invoke({"reason":reason})==old.invoke({"motivo":reason})


def test_exact_active_registry_legacy_execution_and_prompt(network):
    module,_=network
    active=[t.name for t in module.ventas_tools]
    assert active==["transfer_to_billing","request_inventory","transfer_to_support","generar_cotizacion","transfer_to_hardware","consultar_base_conocimiento"]
    assert len(active)==len(set(active))
    legacy={"transferir_a_facturacion","transferir_a_soporte","transferir_a_tecnico","solicitar_inventario"}
    registered=module.build_graph().get_graph().nodes["ventas_tools"].data.tools_by_name
    assert set(registered)==set(active)|legacy
    tree=ast.parse((Path(__file__).resolve().parents[1]/"app/agents/decentralized/ventas.py").read_text(encoding="utf-8"))
    prompt=next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=="SYSTEM_PROMPT" for t in n.targets))
    assert not any(name in prompt for name in legacy)


@pytest.mark.parametrize("target,destination",GROUPS)
@pytest.mark.parametrize("legacy",[False,True])
def test_real_sales_model_call_and_historical_checkpoint(network,target,destination,legacy):
    module,controls=network
    new,old=variants(target,destination)
    tool=old if legacy else new
    event=AIMessage(content="",id="event",tool_calls=[dict(name=tool.name,args={"motivo" if legacy else "reason":"Evaluar"},id="transfer")]);before=deepcopy(event)
    controls["handlers"]["ventas"]=lambda messages:event
    saver=MemorySaver();config={"configurable":{"thread_id":"sales"}}
    state=dict(messages=[HumanMessage(content="Consulta de herramientas")],current_agent="ventas",handoff_history=[],handoff_records=[],handoff_count=0)
    if legacy:
        state["messages"].append(event)
        module.build_graph(checkpointer=saver).update_state(config,state,as_node="ventas")
        result=module.build_graph(checkpointer=saver).invoke(None,config,interrupt_after=["auditar_ventas"])
    else:
        result=module.build_graph(checkpointer=saver).invoke(state,config,interrupt_after=["auditar_ventas"])
    outputs=[m for m in result["messages"] if isinstance(m,ToolMessage)]
    assert len(outputs)==1 and outputs[0].status!="error"
    assert outputs[0].name==tool.name and outputs[0].tool_call_id=="transfer"
    assert result["handoff_history"]==[{"origin":"ventas","destination":destination}]
    assert result["handoff_count"]==1 and result["handoff_records"][0]["reason"]=="Evaluar"
    assert event==before
    assert not any(result.get(k) for k in ["quote_id","payment_id","pending_payment_operation"])


@pytest.mark.parametrize("legacy_first",[False,True])
@pytest.mark.parametrize("failed_first",[False,True])
def test_mixed_batches_choose_first_success_preserving_ids(network,legacy_first,failed_first):
    module,_=network
    first,first_old=variants("billing","facturacion")
    second,second_old=variants("hardware","tecnico")
    calls=[dict(name=(first_old if legacy_first else first).name,args={"motivo" if legacy_first else "reason":" " if failed_first else "Evaluar"},id="first"),
           dict(name=(second if legacy_first else second_old).name,args={"reason" if legacy_first else "motivo":"Otra evaluacion"},id="second")]
    event=AIMessage(content="",id="batch",tool_calls=calls);before=deepcopy(event)
    saver=MemorySaver();config={"configurable":{"thread_id":"batch"}}
    module.build_graph(checkpointer=saver).update_state(config,dict(messages=[HumanMessage(content="Consulta"),event],current_agent="ventas",handoff_history=[],handoff_records=[],handoff_count=0),as_node="ventas")
    result=module.build_graph(checkpointer=saver).invoke(None,config,interrupt_after=["auditar_ventas"])
    outputs=[m for m in result["messages"] if isinstance(m,ToolMessage)]
    assert [(m.name,m.tool_call_id) for m in outputs]==[(c["name"],c["id"]) for c in calls]
    assert (outputs[0].status=="error")==failed_first and outputs[1].status!="error"
    assert result["handoff_history"]==[{"origin":"ventas","destination":"tecnico" if failed_first else "facturacion"}]
    assert result["handoff_count"]==1 and event==before


@pytest.mark.parametrize("legacy",[False,True])
def test_inventory_request_remains_executable_with_new_sales_handoffs(network,legacy):
    module,_=network
    name="solicitar_inventario" if legacy else "request_inventory"
    event=call(name,**{"consulta" if legacy else "query":"Consultar SSD de prueba"});event.id="inventory"
    saver=MemorySaver();config={"configurable":{"thread_id":"inventory"}}
    module.build_graph(checkpointer=saver).update_state(config,dict(messages=[HumanMessage(content="Consulta"),event],current_agent="ventas",handoff_history=[],handoff_records=[],handoff_count=0),as_node="ventas")
    result=module.build_graph(checkpointer=saver).invoke(None,config,interrupt_after=["auditar_ventas"])
    outputs=[m for m in result["messages"] if isinstance(m,ToolMessage)]
    assert len(outputs)==1 and outputs[0].name==name and outputs[0].status!="error"
    assert result["inventory_query"]=="Consultar SSD de prueba" and result["inventory_requested_by"]=="ventas"
    assert result["handoff_history"]==[{"origin":"ventas","destination":"almacen"}]


@pytest.mark.parametrize("progress",[False,True])
def test_sales_cycles_and_legitimate_diagnosis_progress(network,monkeypatch,progress):
    module,controls=network
    monkeypatch.setitem(module.AGENT_NODES,"ventas",lambda state:{"current_agent":"ventas","messages":[call("transfer_to_hardware",reason="Evaluar")]})
    def hardware(messages):
        if progress and isinstance(messages[-1],ToolMessage) and messages[-1].name!="diagnose_issue":
            count=sum(isinstance(m,ToolMessage) and m.name=="diagnose_issue" for m in messages)
            return call("diagnose_issue",symptom="no enciende" if count==0 else "se apaga")
        return call("transfer_to_sales",reason="Evaluar",scope="solo_servicio")
    controls["handlers"]["tecnico"]=hardware
    result=module.build_graph().invoke(dict(messages=[HumanMessage(content="Consulta de herramientas")],current_agent="ventas",quote_scope="solo_servicio"))
    assert result["next_agent"]=="finalizar" and result.get("errors")
    assert result["handoff_count"]==(5 if progress else 2)


@pytest.mark.parametrize("text,name",[("Es compatible con mi laptop","transfer_to_hardware"),("Quiero atencion presencial","transfer_to_support")])
def test_sales_deterministic_producers_keep_english_schema(network,text,name):
    module,_=network
    result=module.build_graph().invoke(dict(messages=[HumanMessage(content=text)],current_agent="ventas"),interrupt_after=["auditar_ventas"])
    events=[c for m in result["messages"] if isinstance(m,AIMessage) for c in m.tool_calls]
    assert len(events)==1 and events[0]["name"]==name
    assert set(events[0]["args"])=={"reason"} and events[0]["args"]["reason"].strip()
    assert result["handoff_count"]==1
