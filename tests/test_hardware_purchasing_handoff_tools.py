from copy import deepcopy
import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver
from pydantic import ValidationError
from app.agents.decentralized.tools import hardware_handoff_tools as hardware, purchasing_handoff_tools as purchasing
from test_software_e2e import network

GROUPS = [
    ("tecnico", "support", "soporte"), ("tecnico", "software", "software"),
    ("tecnico", "sales", "ventas"), ("tecnico", "warehouse", "almacen"),
    ("tecnico", "logistics", "logistica"), ("compras", "sales", "ventas"),
]


def pair(role, target, destination):
    module = hardware if role == "tecnico" else purchasing
    return getattr(module, "transfer_to_" + target), next(t for t in module.legacy_handoff_tools if t.name == "transferir_a_" + destination)


def args(role, target, legacy=False, **changes):
    value = {"reason": "Evaluar"}
    if role == "tecnico" and target == "sales":
        value.update(scope="solo_servicio", part_name="", quantity=1)
    if target == "warehouse":
        value.update(part_name="SSD de prueba", quantity=2)
    value.update(changes)
    mapping = dict(reason="motivo", scope="alcance", part_name="nombre_repuesto", quantity="cantidad")
    return {mapping[k] if legacy else k: v for k, v in value.items()}


@pytest.mark.parametrize("role,target,destination", GROUPS)
def test_schemas_and_local_results(role, target, destination):
    new, old = pair(role, target, destination)
    for tool, legacy in [(new, False), (old, True)]:
        schema = tool.tool_call_schema.model_json_schema()
        assert set(schema["properties"]) == set(args(role, target, legacy))
        assert set(schema["required"]) == ({"motivo" if legacy else "reason"} | ({"alcance" if legacy else "scope"} if role == "tecnico" and target == "sales" else set()) | ({"nombre_repuesto" if legacy else "part_name"} if target == "warehouse" else set()))
    assert new.invoke(args(role,target)) == old.invoke(args(role,target,True))


@pytest.mark.parametrize("target", ["sales", "warehouse"])
@pytest.mark.parametrize("quantity", [0, -1, 3])
def test_quantity_validation_is_unchanged(target, quantity):
    new, old = pair("tecnico", target, "ventas" if target == "sales" else "almacen")
    def invoke(tool, legacy):
        return tool.invoke(args("tecnico", target, legacy, quantity=quantity))
    if target == "sales" and quantity <= 0:
        for tool, legacy in [(new,False),(old,True)]:
            with pytest.raises(ValueError): invoke(tool,legacy)
    else:
        assert invoke(new,False) == invoke(old,True)


@pytest.mark.parametrize("scope", ["solo_servicio", "repuestos", "sin_determinar", "invalid"])
def test_sales_scope_values_preserved(scope):
    new, old = pair("tecnico", "sales", "ventas")
    if scope == "invalid":
        for tool, legacy in [(new,False),(old,True)]:
            with pytest.raises(ValidationError): tool.invoke(args("tecnico","sales",legacy,scope=scope))
    else:
        assert new.invoke(args("tecnico","sales",scope=scope)) == old.invoke(args("tecnico","sales",True,scope=scope))


def test_blank_part_and_purchasing_reason_preserve_local_validation():
    assert hardware.transfer_to_warehouse.invoke(dict(reason="Evaluar",part_name="  ")) == {"error":"El nombre del repuesto es obligatorio."}
    with pytest.raises(ValueError): purchasing.transfer_to_sales.invoke(dict(reason="  "))


@pytest.mark.parametrize("role", ["tecnico", "compras"])
def test_exact_active_and_toolnode_registries(network,role):
    module,_ = network
    active = getattr(module, role + "_tools")
    names = [t.name for t in active]
    expected = {"transfer_to_" + target for origin,target,_ in GROUPS if origin == role}
    assert {n for n in names if n.startswith("transfer_to_")} == expected
    assert not any(n.startswith("transferir_a_") for n in names)
    assert len(names) == len(set(names))
    legacy = {"transferir_a_" + destination for origin,_,destination in GROUPS if origin == role}
    extra = {"diagnosticar_problema"} if role == "tecnico" else {"consultar_fuentes_abastecimiento"}
    assert set(module.build_graph().get_graph().nodes[role+"_tools"].data.tools_by_name) == set(names) | legacy | extra


@pytest.mark.parametrize("legacy", [True,False])
@pytest.mark.parametrize("target,destination", [("support","soporte"),("software","software"),("sales","ventas"),("warehouse","almacen"),("logistics","logistica")])
def test_pending_checkpoint_executes_both_names_without_rewriting(network,legacy,target,destination):
    module,_ = network
    new,old = pair("tecnico",target,destination)
    event = AIMessage(content="", id="event", tool_calls=[dict(name=(old if legacy else new).name,args=args("tecnico",target,legacy),id="pending")])
    original = deepcopy(event)
    saver = MemorySaver()
    config = {"configurable":{"thread_id":"pending-hardware"}}
    graph = module.build_graph(checkpointer=saver)
    graph.update_state(config,dict(messages=[HumanMessage(content="Consultar SSD de prueba"),event],current_agent="tecnico",handoff_count=0,handoff_history=[],handoff_records=[]),as_node="tecnico")
    result = module.build_graph(checkpointer=saver).invoke(None,config,interrupt_after=["auditar_tecnico"])
    outputs=[m for m in result["messages"] if isinstance(m,ToolMessage)]
    assert len(outputs)==1 and outputs[0].status != "error"
    assert outputs[0].tool_call_id=="pending" and outputs[0].name==(old if legacy else new).name
    assert result["handoff_history"]==[{"origin":"tecnico","destination":destination}]
    assert result["handoff_count"]==1 and event==original


@pytest.mark.parametrize("role", ["tecnico", "compras"])
@pytest.mark.parametrize("legacy_first", [False, True])
def test_mixed_batch_checkpoint_selects_first_successful_and_preserves_ids(network,role,legacy_first):
    from test_compras import value
    module,_ = network
    target,destination = ("support","soporte") if role == "tecnico" else ("sales","ventas")
    new,old = pair(role,target,destination)
    calls = [dict(name=(old if legacy else new).name,args=args(role,target,legacy),id=str(index))
             for index,legacy in enumerate([legacy_first,not legacy_first])]
    event = AIMessage(content="",id="batch",tool_calls=calls)
    before = deepcopy(event)
    state = value() if role == "compras" else dict(messages=[HumanMessage(content="Consulta")])
    state.update(messages=[*state["messages"],event],current_agent=role,handoff_count=0,handoff_history=[],handoff_records=[])
    saver = MemorySaver()
    config = {"configurable":{"thread_id":"mixed"}}
    module.build_graph(checkpointer=saver).update_state(config,state,as_node=role)
    result = module.build_graph(checkpointer=saver).invoke(None,config,interrupt_after=["auditar_"+role])
    outputs = [m for m in result["messages"] if isinstance(m,ToolMessage)]
    assert [(m.name,m.tool_call_id) for m in outputs] == [(c["name"],c["id"]) for c in calls]
    assert all(m.status != "error" for m in outputs)
    assert result["handoff_history"] == [{"origin":role,"destination":destination}]
    assert result["handoff_count"] == 1 and event == before


@pytest.mark.parametrize("scope",["sin_determinar","repuestos"])
def test_hardware_sales_audit_still_blocks_unresolved_parts(network,scope):
    module,controls=network
    controls["handlers"]["tecnico"] = lambda messages: AIMessage(content="",tool_calls=[dict(name="transfer_to_sales",args=dict(reason="Evaluar",scope=scope),id="guard")])
    result = module.build_graph().invoke(dict(messages=[HumanMessage(content="Consulta")],current_agent="tecnico"))
    assert not result["handoff_history"] and not result.get("quote_id")
    assert not result.get("required_parts")


@pytest.mark.parametrize("progress",[False,True])
def test_hardware_english_cycle_and_new_progress(network,progress):
    from test_software_e2e import call
    module,controls=network
    def hardware_model(messages):
        if progress and isinstance(messages[-1],ToolMessage) and messages[-1].name != "diagnose_issue":
            count=sum(isinstance(m,ToolMessage) and m.name=="diagnose_issue" for m in messages)
            return call("diagnose_issue",symptom="no enciende" if count==0 else "se apaga")
        return call("transfer_to_software",reason="Evaluar")
    controls["handlers"]["tecnico"]=hardware_model
    controls["handlers"]["software"]=lambda messages: call("transfer_to_hardware",reason="Evaluar")
    result=module.build_graph().invoke(dict(messages=[HumanMessage(content="Consulta")],current_agent="tecnico"))
    assert result["next_agent"]=="finalizar"
    assert result["handoff_count"] == (5 if progress else 2)
    assert result.get("errors")
