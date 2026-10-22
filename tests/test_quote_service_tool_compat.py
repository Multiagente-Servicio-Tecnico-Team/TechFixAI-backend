from copy import deepcopy
import ast
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver
from pydantic import ValidationError

from app.agents.decentralized import handoffs
from app.agents.decentralized.tools.ventas_tools import generar_cotizacion, identify_quote_service
from test_software_e2e import network, call

NAMES = [(generar_cotizacion,"servicio"),(identify_quote_service,"service")]
FROZEN = [
    ("diagnostico","d17a51b25afad402cb945e56db0752091ea35a07261ef53104bd6e80f1987d81"),
    ("mantenimiento","ff2479f82805f8c129e9e0a4caf890fbf6d85c2a412ce23f195e92e4692f9e84"),
    ("otro servicio","1258f579228787e506841c135e940cc40d0c57897f552f5ba6f215756038c726"),
]


def quote_state(service="diagnostico",english=False):
    tool,key=NAMES[english]
    event=AIMessage(content="",id="event",tool_calls=[dict(name=tool.name,args={key:service},id="call")])
    result=ToolMessage(content=tool.invoke({key:service}),name=tool.name,tool_call_id="call")
    return dict(messages=[HumanMessage(content="Consulta de prueba"),event,result],request_revision=2)


@pytest.mark.parametrize("tool,key",NAMES)
def test_exact_public_schema_and_description(tool,key):
    schema=tool.tool_call_schema.model_json_schema()
    assert set(schema["properties"])==set(schema["required"])=={key}
    assert schema["properties"][key]["type"]=="string"
    assert tool.description==generar_cotizacion.description
    with pytest.raises(ValidationError):tool.invoke({"service" if key=="servicio" else "servicio":"diagnostico"})


@pytest.mark.parametrize("service",["diagnostico","mantenimiento","reparacion","instalacion","  DIAGNOSTICO  ","otro servicio",""])
def test_identical_outputs_without_new_prices_or_persistence(service):
    assert identify_quote_service.invoke({"service":service})==generar_cotizacion.invoke({"servicio":service})


@pytest.mark.parametrize("value",[None,2,True,[]])
def test_public_validation_errors_remain_equivalent(value):
    errors=[]
    for tool,key in NAMES:
        with pytest.raises(ValidationError) as captured:tool.invoke({key:value})
        errors.append([(error["type"],error["msg"]) for error in captured.value.errors()])
    assert errors[0]==errors[1]


@pytest.mark.parametrize("service,expected",FROZEN)
def test_frozen_legacy_hash_and_new_alias_match(service,expected):
    legacy=quote_state(service);english=quote_state(service,True)
    before=deepcopy((legacy,english))
    assert handoffs.progress_token(legacy)==handoffs.progress_token(english)==expected
    assert (legacy,english)==before


@pytest.mark.parametrize("style",["english","mixed","legacy_repeat"])
def test_equal_outputs_do_not_invent_progress_when_arguments_names_or_ids_change(style):
    state=quote_state()
    extra=quote_state(english=style!="legacy_repeat")["messages"][1:]
    extra[0].id="other-event";extra[0].tool_calls[0]["id"]="other-call";extra[1].tool_call_id="other-call"
    changed={**state,"messages":extra if style=="english" else [*state["messages"],*extra]}
    if style=="english":changed["messages"]=[state["messages"][0],*extra]
    before=deepcopy(changed)
    assert handoffs.progress_token(changed)==handoffs.progress_token(state)
    assert changed==before


@pytest.mark.parametrize("different",["mantenimiento","otro servicio"])
def test_real_response_changes_remain_progress(different):
    assert handoffs.progress_token(quote_state())!=handoffs.progress_token(quote_state(different,True))


@pytest.mark.parametrize("name",["diagnose_issue","get_financial_capabilities","unrelated_tool"])
def test_other_tool_names_are_not_normalized(name):
    state=quote_state(english=True)
    other=deepcopy(state);other["messages"][-1].name=name
    assert handoffs.progress_token(state)!=handoffs.progress_token(other)


@pytest.mark.parametrize("progress",[False,True])
def test_repeat_handoff_cannot_bypass_cycle_record_by_switching_quote_tool_name(progress):
    legacy=quote_state()
    record=handoffs.make_handoff_record(legacy,"ventas","tecnico","Evaluar",handoffs.ALLOWED_HANDOFFS)
    resumed={**quote_state("mantenimiento" if progress else "diagnostico",True),"handoff_records":[record]}
    before=deepcopy(resumed)
    if progress:
        next_record=handoffs.make_handoff_record(resumed,"ventas","tecnico","Evaluar",handoffs.ALLOWED_HANDOFFS)
        assert next_record["progress_token"]!=record["progress_token"]
    else:
        with pytest.raises(ValueError,match="repetida"):
            handoffs.make_handoff_record(resumed,"ventas","tecnico","Evaluar",handoffs.ALLOWED_HANDOFFS)
    assert resumed==before


def test_failed_quote_result_is_still_excluded_from_progress():
    state=quote_state(english=True);state["messages"][-1].status="error"
    assert handoffs.progress_token(state)==handoffs.progress_token({**state,"messages":state["messages"][:1]})


def test_active_and_legacy_registries_and_prompt_are_coherent(network):
    module,_=network
    names=[tool.name for tool in module.ventas_tools]
    assert names.count("identify_quote_service")==1 and "generar_cotizacion" not in names
    assert len(names)==len(set(names))
    registered=module.build_graph().get_graph().nodes["ventas_tools"].data.tools_by_name
    assert {"identify_quote_service","generar_cotizacion"}<=set(registered)
    tree=ast.parse((Path(__file__).resolve().parents[1]/"app/agents/decentralized/sales.py").read_text(encoding="utf-8"))
    prompt=next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=="SYSTEM_PROMPT" for t in n.targets))
    assert "identify_quote_service" in prompt and "generar_cotizacion" not in prompt


@pytest.mark.parametrize("style",["legacy","english","mixed","mixed_error"])
def test_toolnode_checkpoint_batches_preserve_calls_ids_and_history(network,monkeypatch,style):
    module,_=network
    calls=[dict(name=tool.name,args={key:(None if style=="mixed_error" and index==0 else "diagnostico")},id=str(index)) for index,(tool,key) in enumerate(NAMES)]
    if style in {"legacy","english"}:calls=[calls[style=="english"]]
    event=AIMessage(content="",id="batch",tool_calls=calls);before=deepcopy(event)
    saver=MemorySaver();config={"configurable":{"thread_id":"quotes"}}
    graph=module.build_graph(checkpointer=saver)
    history=[{"origin":"soporte","destination":"ventas"}]
    graph.update_state(config,dict(messages=[HumanMessage(content="Consulta de prueba"),event],current_agent="ventas",request_revision=2,handoff_history=history,handoff_count=1),as_node="ventas")
    def forbidden(state):raise AssertionError("Turn preparation must not run during resume")
    monkeypatch.setattr(module,"prepare_turn",forbidden)
    result=module.build_graph(checkpointer=saver).invoke(None,config,interrupt_after=["auditar_ventas"])
    outputs=[m for m in result["messages"] if isinstance(m,ToolMessage)]
    assert [(m.name,m.tool_call_id) for m in outputs]==[(c["name"],c["id"]) for c in calls]
    assert sum(m.status=="error" for m in outputs)==(1 if style=="mixed_error" else 0)
    assert all(m.content==generar_cotizacion.invoke({"servicio":"diagnostico"}) for m in outputs if m.status!="error")
    assert event==before and result["handoff_history"]==history and result["handoff_count"]==1
    assert not result.get("quote_id") and not result.get("payment_id")


@pytest.mark.parametrize("english",[False,True])
def test_sales_context_keeps_original_call_result_pair(network,english):
    import importlib
    network_module,_=network
    sales=importlib.import_module("app.agents.decentralized.ventas")
    state=quote_state(english=english);before=deepcopy(state)
    context=sales.build_sales_context(state)
    assert state["messages"][1] in context and state["messages"][2] in context
    assert next(m for m in context if isinstance(m,AIMessage)) is state["messages"][1]
    assert next(m for m in context if isinstance(m,ToolMessage)) is state["messages"][2]
    assert state==before


def test_sales_model_can_call_only_active_english_quote_variant(network):
    module,controls=network
    event=call("identify_quote_service",service="mantenimiento");event.id="event"
    controls["handlers"]["ventas"]=lambda messages:event
    result=module.build_graph().invoke(dict(messages=[HumanMessage(content="Consulta de prueba")],current_agent="ventas"),interrupt_after=["auditar_ventas"])
    outputs=[m for m in result["messages"] if isinstance(m,ToolMessage)]
    assert len(outputs)==1 and outputs[0].name=="identify_quote_service" and outputs[0].status!="error"
    assert outputs[0].tool_call_id==event.tool_calls[0]["id"]
    assert not result.get("quote_id") and not result.get("payment_id")
