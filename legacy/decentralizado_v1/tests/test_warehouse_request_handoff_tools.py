from copy import deepcopy
import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver
from pydantic import ValidationError
from app.agents.decentralized.tools import warehouse_handoff_tools as warehouse, inventory_request_tools as inventory
from app.agents.decentralized.handoffs import progress_token
from test_software_e2e import network
from test_compras import value

GROUPS=[("almacen",warehouse.transfer_to_sales,warehouse.legacy_handoff_tools[0],"ventas","reason","motivo"),
        ("almacen",warehouse.transfer_to_purchasing,warehouse.legacy_handoff_tools[1],"compras","reason","motivo"),
        ("ventas",inventory.request_inventory,inventory.legacy_inventory_request_tools[0],"almacen","query","consulta")]


@pytest.mark.parametrize("role,new,old,destination,key,oldkey",GROUPS)
def test_schemas_and_equivalent_public_results(role,new,old,destination,key,oldkey):
    for tool,parameter,wrong in [(new,key,oldkey),(old,oldkey,key)]:
        schema=tool.tool_call_schema.model_json_schema()
        assert set(schema["properties"])==set(schema["required"])=={parameter}
        with pytest.raises(ValidationError):tool.invoke({wrong:"Evaluar"})
        with pytest.raises(ValidationError):tool.invoke({parameter:None})
    assert new.invoke({key:"  Evaluar  "})==old.invoke({oldkey:"  Evaluar  "})


@pytest.mark.parametrize("role,new,old,destination,key,oldkey",GROUPS)
def test_blank_arguments_preserve_each_local_contract(role,new,old,destination,key,oldkey):
    if destination=="compras":
        for tool,k in [(new,key),(old,oldkey)]:
            with pytest.raises(ValueError):tool.invoke({k:" "})
    else:
        assert new.invoke({key:" "})==old.invoke({oldkey:" "})
    if role=="ventas":
        assert new.invoke({key:"SSD"})=={"accion":"CONSULTAR_DISPONIBILIDAD","consulta":"SSD"}


@pytest.mark.parametrize("role",["almacen","ventas"])
def test_exact_active_and_legacy_registries(network,role):
    module,_=network
    active=[t.name for t in getattr(module,role+"_tools")]
    if role=="almacen":
        assert active==["check_inventory","transfer_to_sales","transfer_to_purchasing"]
        legacy={"transferir_a_ventas","transferir_a_compras","consultar_inventario"}
    else:
        assert "request_inventory" in active and "solicitar_inventario" not in active
        assert {n for n in active if n.startswith("transfer_to_")}=={"transfer_to_billing","transfer_to_support","transfer_to_hardware"}
        assert not any(n.startswith("transferir_a_") for n in active)
        legacy={"solicitar_inventario","transferir_a_facturacion","transferir_a_soporte","transferir_a_tecnico","generar_cotizacion"}
    assert len(active)==len(set(active))
    assert set(module.build_graph().get_graph().nodes[role+"_tools"].data.tools_by_name)==set(active)|legacy


@pytest.mark.parametrize("role,new,old,destination,key,oldkey",GROUPS)
@pytest.mark.parametrize("legacy",[False,True])
def test_pending_checkpoint_keeps_ids_audit_and_results(network,role,new,old,destination,key,oldkey,legacy):
    module,_=network
    state=value(stock=3 if destination=="ventas" else 0,quantity=1) if role=="almacen" else dict(messages=[HumanMessage(content="Consultar SSD de prueba")])
    tool=old if legacy else new
    event=AIMessage(content="",id="event",tool_calls=[dict(name=tool.name,args={oldkey if legacy else key:"Consultar SSD de prueba"},id="pending")]);before=deepcopy(event)
    state.update(messages=[*state["messages"],event],current_agent=role,handoff_history=[],handoff_records=[],handoff_count=0)
    saver=MemorySaver();config={"configurable":{"thread_id":"pending"}}
    module.build_graph(checkpointer=saver).update_state(config,state,as_node=role)
    result=module.build_graph(checkpointer=saver).invoke(None,config,interrupt_after=["auditar_"+role])
    outputs=[m for m in result["messages"] if isinstance(m,ToolMessage)]
    assert len(outputs)==1 and outputs[0].status!="error" and outputs[0].tool_call_id=="pending" and outputs[0].name==tool.name
    assert result["handoff_history"]==[{"origin":role,"destination":destination}] and result["handoff_count"]==1
    assert event==before
    if role=="ventas":assert result["inventory_query"]=="Consultar SSD de prueba" and result["inventory_requested_by"]=="ventas"
    assert not any(result.get(k) for k in ["quote_id","payment_id","purchase_order_id"])


@pytest.mark.parametrize("legacy_first",[False,True])
@pytest.mark.parametrize("role",["almacen","ventas"])
def test_mixed_batches_preserve_first_success_and_tokens(network,role,legacy_first):
    module,_=network
    group=GROUPS[0] if role=="almacen" else GROUPS[2]
    _,new,old,destination,key,oldkey=group
    calls=[dict(name=(old if legacy else new).name,args={oldkey if legacy else key:"Evaluar"},id=str(index)) for index,legacy in enumerate([legacy_first,not legacy_first])]
    event=AIMessage(content="",id="batch",tool_calls=calls);before=deepcopy(event)
    state=value(stock=3,quantity=1) if role=="almacen" else dict(messages=[HumanMessage(content="Consulta")])
    state.update(messages=[*state["messages"],event],current_agent=role,handoff_history=[],handoff_records=[],handoff_count=0)
    saver=MemorySaver();config={"configurable":{"thread_id":"batch"}}
    module.build_graph(checkpointer=saver).update_state(config,state,as_node=role)
    result=module.build_graph(checkpointer=saver).invoke(None,config,interrupt_after=["auditar_"+role])
    outputs=[m for m in result["messages"] if isinstance(m,ToolMessage)]
    assert [(m.name,m.tool_call_id) for m in outputs]==[(c["name"],c["id"]) for c in calls]
    assert all(m.status!="error" for m in outputs)
    assert result["handoff_history"]==[{"origin":role,"destination":destination}] and result["handoff_count"]==1
    assert event==before
    old_state={**state,"messages":[state["messages"][0],ToolMessage(content=outputs[0].content,name=old.name,tool_call_id="old")]}
    new_state={**state,"messages":[state["messages"][0],ToolMessage(content=outputs[0].content,name=new.name,tool_call_id="new")]}
    assert progress_token(old_state)==progress_token(new_state)


@pytest.mark.parametrize("legacy",[False,True])
@pytest.mark.parametrize("change",[{"inventory_revision":1},{"inventory_results":[]},{"errors":["Error de inventario"]}])
def test_stale_or_missing_inventory_blocks_warehouse_transfer(network,legacy,change):
    module,_=network
    state=value(stock=3,quantity=1);state.update(change)
    tool=warehouse.legacy_handoff_tools[0] if legacy else warehouse.transfer_to_sales
    event=AIMessage(content="",id="event",tool_calls=[dict(name=tool.name,args={"motivo" if legacy else "reason":"Evaluar"},id="guard")])
    state.update(messages=[*state["messages"],event],current_agent="almacen",handoff_history=[],handoff_records=[],handoff_count=0)
    saver=MemorySaver();config={"configurable":{"thread_id":"guard"}}
    module.build_graph(checkpointer=saver).update_state(config,state,as_node="almacen")
    result=module.build_graph(checkpointer=saver).invoke(None,config,interrupt_after=["auditar_almacen"])
    assert result["handoff_count"]==0 and not result.get("quote_id")
    assert result["next_agent"]=="finalizar"


@pytest.mark.parametrize("legacy",[False,True])
def test_blank_inventory_request_is_not_an_authorized_handoff(network,legacy):
    module,_=network
    tool=inventory.legacy_inventory_request_tools[0] if legacy else inventory.request_inventory
    event=AIMessage(content="",id="event",tool_calls=[dict(name=tool.name,args={"consulta" if legacy else "query":" "},id="invalid")])
    saver=MemorySaver();config={"configurable":{"thread_id":"invalid"}}
    module.build_graph(checkpointer=saver).update_state(config,dict(messages=[HumanMessage(content="Consulta"),event],current_agent="ventas",handoff_history=[],handoff_records=[],handoff_count=0),as_node="ventas")
    result=module.build_graph(checkpointer=saver).invoke(None,config,interrupt_after=["auditar_ventas"])
    assert result["handoff_count"]==0 and result["next_agent"]=="finalizar"


@pytest.mark.parametrize("progress",[False,True])
def test_warehouse_inventory_handoff_cycles_require_real_progress(network,progress):
    from app.agents.decentralized.handoffs import make_handoff_record
    state=value(stock=3,quantity=1)
    old=warehouse.legacy_handoff_tools[0];new=warehouse.transfer_to_sales
    old_message=ToolMessage(content=old.invoke({"motivo":"Evaluar"}),name=old.name,tool_call_id="old")
    original={**state,"messages":[*state["messages"],old_message]}
    record=make_handoff_record(original,"almacen","ventas","Evaluar",network[0].AGENT_NODES)
    current={**state,"handoff_records":[record],"messages":[*state["messages"],ToolMessage(content=new.invoke({"reason":"Evaluar"}),name=new.name,tool_call_id="new")]}
    if progress:
        current["messages"].append(ToolMessage(content='{"stock":4,"found":true}',name="check_inventory",tool_call_id="verified"))
        result=make_handoff_record(current,"almacen","ventas","Evaluar",network[0].AGENT_NODES)
        assert result["progress_token"]!=record["progress_token"]
    else:
        with pytest.raises(ValueError,match="repetida"):
            make_handoff_record(current,"almacen","ventas","Evaluar",network[0].AGENT_NODES)
