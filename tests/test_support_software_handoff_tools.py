import ast
from copy import deepcopy
from pathlib import Path
import re

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver
from pydantic import ValidationError

from app.agents.decentralized import handoffs
from app.agents.decentralized.tools import support_handoff_tools as support
from app.agents.decentralized.tools import software_handoff_tools as software
from test_software import agent, state as software_state
from test_software_e2e import network, call


GROUPS = [
    ("soporte", "transfer_to_hardware", "transferir_a_tecnico", "tecnico"),
    ("soporte", "transfer_to_sales", "transferir_a_ventas", "ventas"),
    ("soporte", "transfer_to_software", "transferir_a_software", "software"),
    ("soporte", "transfer_to_billing", "transferir_a_facturacion", "facturacion"),
    ("soporte", "transfer_to_logistics", "transferir_a_logistica", "logistica"),
    ("soporte", "transfer_to_warranty", "transferir_a_garantia", "garantia"),
    ("software", "transfer_to_support", "transferir_a_soporte", "soporte"),
    ("software", "transfer_to_hardware", "transferir_a_tecnico", "tecnico"),
    ("software", "transfer_to_sales", "transferir_a_ventas", "ventas"),
    ("software", "transfer_to_logistics", "transferir_a_logistica", "logistica"),
]


def variants(origin, name, old):
    module = support if origin == "soporte" else software
    return getattr(module, name), next(tool for tool in module.legacy_handoff_tools if tool.name == old)


def arguments(origin, name, reason="Evaluar", legacy=False):
    result = {"motivo" if legacy else "reason": reason}
    if origin == "software" and name == "transfer_to_sales":
        result["alcance" if legacy else "scope"] = "solo_servicio"
    return result


@pytest.mark.parametrize("origin,name,old,destination", GROUPS)
def test_new_and_legacy_schemas_are_exact(origin, name, old, destination):
    current, previous = variants(origin, name, old)
    for tool, legacy in [(current, False), (previous, True)]:
        expected = set(arguments(origin, name, legacy=legacy))
        schema = tool.tool_call_schema.model_json_schema()
        assert tool.name == (old if legacy else name)
        assert set(schema["properties"]) == set(schema["required"]) == expected
        with pytest.raises(ValidationError):
            tool.invoke(arguments(origin, name, legacy=not legacy))
    assert handoffs.HANDOFF_TOOLS[name] == handoffs.HANDOFF_TOOLS[old] == destination


@pytest.mark.parametrize("origin,name,old,destination", GROUPS)
@pytest.mark.parametrize("reason", ["Evaluar", "  Revisar  ", ""])
def test_wrappers_preserve_local_results_and_reason_validation(origin, name, old, destination, reason):
    current, previous = variants(origin, name, old)
    try:
        expected = previous.invoke(arguments(origin, name, reason, legacy=True))
    except ValueError as error:
        with pytest.raises(type(error), match=re.escape(str(error))):
            current.invoke(arguments(origin, name, reason))
    else:
        assert current.invoke(arguments(origin, name, reason)) == expected


@pytest.mark.parametrize("scope", ["repuestos", "sin_determinar", None])
def test_software_sales_scope_is_restricted_for_both_variants(scope):
    new, old = variants("software", "transfer_to_sales", "transferir_a_ventas")
    for tool, args in [(new, dict(reason="Evaluar", scope=scope)), (old, dict(motivo="Evaluar", alcance=scope))]:
        with pytest.raises(ValidationError):
            tool.invoke(args)
    result = new.invoke(dict(reason="Evaluar", scope="solo_servicio"))
    assert result == dict(accion="SOLICITAR_COTIZACION", motivo="Evaluar", alcance="solo_servicio", nombre_repuesto="", cantidad=1)


@pytest.mark.parametrize("origin", ["soporte", "software"])
def test_exact_active_and_execution_registries_and_prompt_references(network, origin):
    module, _ = network
    active = getattr(module, f"{origin}_tools")
    names = [tool.name for tool in active]
    expected = {name for role, name, _, _ in GROUPS if role == origin}
    legacy = {old for role, _, old, _ in GROUPS if role == origin}
    assert expected == {name for name in names if name.startswith("transfer_to_")}
    assert not legacy & set(names) and len(names) == len(set(names))
    registered = set(module.build_graph().get_graph().nodes[f"{origin}_tools"].data.tools_by_name)
    assert registered == set(names) | legacy | ({"consultar_estado_ticket"} if origin == "soporte" else set())
    tree = ast.parse((Path(__file__).resolve().parents[1] / f"app/agents/decentralized/{origin}.py").read_text(encoding="utf-8"))
    prompt = next(ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "SYSTEM_PROMPT" for target in node.targets))
    assert not any(name in prompt for name in legacy)


@pytest.mark.parametrize("origin,name,old,destination", GROUPS)
@pytest.mark.parametrize("legacy", [False, True])
def test_real_graph_executes_each_local_variant_without_changing_destination(network, origin, name, old, destination, legacy):
    module, controls = network
    text = "Consulta de herramientas"
    extra = {}
    if origin == "software" and destination == "ventas":
        text = "Confirmo Evaluación del editor. Cotiza solo servicio sin repuestos"
        extra = dict(request_revision=2, technical_assessment={"software_diagnosis": "Evaluación del editor"})
    event = AIMessage(content="", tool_calls=[dict(name=old if legacy else name,
        args=arguments(origin, name, legacy=legacy), id="local-handoff")], id="local-event")
    before = deepcopy(event)
    controls["handlers"][origin] = lambda messages: event
    result = module.build_graph().invoke(dict(messages=[HumanMessage(content=text)], current_agent=origin, **extra))
    outputs = [message for message in result["messages"] if isinstance(message, ToolMessage)]
    assert len(outputs) == 1 and outputs[0].name == (old if legacy else name)
    assert outputs[0].tool_call_id == "local-handoff" and outputs[0].status != "error"
    assert result["handoff_history"] == [{"origin": origin, "destination": destination}]
    assert result["handoff_records"][0]["reason"] == "Evaluar"
    assert result["handoff_count"] == 1 and event == before
    assert not any(result.get(key) for key in ["quote_id", "payment_id", "logistics_record_id", "warranty_claim_id"])


@pytest.mark.parametrize("origin", ["soporte", "software"])
@pytest.mark.parametrize("first_legacy", [False, True])
def test_mixed_pending_batches_preserve_order_ids_and_one_selected_transfer(network, origin, first_legacy):
    module, _ = network
    first_new, first_old, destination = (("transfer_to_hardware", "transferir_a_tecnico", "tecnico") if origin == "soporte"
                                       else ("transfer_to_support", "transferir_a_soporte", "soporte"))
    second_new, second_old = (("transfer_to_software", "transferir_a_software") if origin == "soporte"
                              else ("transfer_to_hardware", "transferir_a_tecnico"))
    calls = [dict(name=first_old if first_legacy else first_new, args=arguments(origin, first_new, legacy=first_legacy), id="first"),
             dict(name=second_new if first_legacy else second_old, args=arguments(origin, second_new, legacy=not first_legacy), id="second")]
    event = AIMessage(content="", tool_calls=calls, id="batch")
    before = deepcopy(event)
    saver = MemorySaver()
    config = {"configurable": {"thread_id": "mixed-handoff"}}
    graph = module.build_graph(checkpointer=saver)
    graph.update_state(config, dict(messages=[HumanMessage(content="Consulta de herramientas", id="user"), event],
        current_agent=origin, handoff_history=[], handoff_count=0, handoff_records=[]), as_node=origin)
    result = module.build_graph(checkpointer=saver).invoke(None, config)
    outputs = [message for message in result["messages"] if isinstance(message, ToolMessage)]
    assert [(message.name, message.tool_call_id) for message in outputs] == [(call["name"], call["id"]) for call in calls]
    assert all(message.status != "error" for message in outputs)
    assert result["handoff_history"] == [{"origin": origin, "destination": destination}] and result["handoff_count"] == 1
    assert event == before


@pytest.mark.parametrize("valid", [False, True])
def test_software_model_sales_guard_uses_english_schema(agent, valid):
    module, regular, _, bindings = agent
    event = AIMessage(content="", tool_calls=[dict(name="transfer_to_sales", args=dict(reason="Evaluar", scope="solo_servicio"), id="sales")])
    regular.response = event
    state = software_state("Confirmo Evaluación del editor. Cotiza solo servicio sin repuestos", request_revision=2)
    if valid:
        state["technical_assessment"] = {"software_diagnosis": "Evaluación del editor"}
    result = module.software_node(state)
    assert bool(result["messages"][0].tool_calls) is valid
    assert bindings[0][0] == ["transfer_to_support", "transfer_to_hardware", "transfer_to_sales", "consultar_base_conocimiento", "transfer_to_logistics"]


def test_all_agents_expose_english_transfer_tools(network):
    module, _ = network
    for role in module.AGENT_NODES:
        names = {tool.name for tool in getattr(module, f"{role}_tools")}
        assert any(name.startswith("transfer_to_") for name in names)
        assert not any(name.startswith("transferir_a_") for name in names)
    assert module.MAX_HANDOFFS == 5 and module.MAX_TOOL_ITERATIONS == 6
    assert support.transfer_to_hardware.invoke({"reason": ""}) == "TRANSFERIR_TECNICO: "
    with pytest.raises(ValueError):
        software.transfer_to_hardware.invoke({"reason": ""})


@pytest.mark.parametrize("progress", [False, True])
def test_english_software_handoff_preserves_cycles_and_legitimate_progress(network, progress):
    module, controls = network
    controls["handlers"]["software"] = lambda messages: call("transfer_to_hardware", reason="Evaluar")
    def hardware(messages):
        if progress and isinstance(messages[-1], ToolMessage) and messages[-1].name != "diagnose_issue":
            count = sum(isinstance(message, ToolMessage) and message.name == "diagnose_issue" for message in messages)
            return call("diagnose_issue", symptom="no enciende" if count == 0 else "se apaga")
        return call("transferir_a_software", motivo="Evaluar")
    controls["handlers"]["tecnico"] = hardware
    result = module.build_graph().invoke(dict(messages=[HumanMessage(content="Consulta de herramientas")], current_agent="software"))
    records = [record for record in result["handoff_records"] if record["origin"] == "software"]
    assert result["next_agent"] == "finalizar"
    if progress:
        assert result["handoff_count"] == 5
        assert len({record["progress_token"] for record in records}) == len(records) > 1
        assert any("Límite" in error for error in result["errors"])
    else:
        assert result["handoff_count"] == 2
        assert any("repetida" in error for error in result["errors"])
