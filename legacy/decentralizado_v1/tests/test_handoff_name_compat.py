from copy import deepcopy
import json
import sys
from typing import Literal

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import StructuredTool
from langgraph.checkpoint.memory import MemorySaver

from app.agents.decentralized import handoffs, policy
from test_software import agent, state as software_state
from test_software_e2e import network


PAIRS = [
    ("transferir_a_soporte", "transfer_to_support", "soporte"),
    ("transferir_a_tecnico", "transfer_to_hardware", "tecnico"),
    ("transferir_a_software", "transfer_to_software", "software"),
    ("transferir_a_ventas", "transfer_to_sales", "ventas"),
    ("transferir_a_almacen", "transfer_to_warehouse", "almacen"),
    ("transferir_a_compras", "transfer_to_purchasing", "compras"),
    ("transferir_a_facturacion", "transfer_to_billing", "facturacion"),
    ("transferir_a_logistica", "transfer_to_logistics", "logistica"),
    ("transferir_a_garantia", "transfer_to_warranty", "garantia"),
    ("solicitar_inventario", "request_inventory", "almacen"),
]
ALIASES = {old: new for old, new, _ in PAIRS}
KEYS = {"motivo": "reason", "alcance": "scope", "nombre_repuesto": "part_name",
        "cantidad": "quantity", "consulta": "query", "accion": "action"}


def messages(name, payload, identifier="transfer", with_args=True):
    call = AIMessage(content="", tool_calls=[dict(name=name, args=deepcopy(payload), id=identifier)], id="call-"+identifier)
    result = ToolMessage(content=json.dumps(payload), name=name, tool_call_id=identifier)
    return [call, result] if with_args else [result]


def english(payload):
    return {KEYS.get(key, key): value for key, value in payload.items()}


@pytest.mark.parametrize("old,new,destination", PAIRS)
def test_aliases_share_destination_reason_and_progress_without_mutation(old, new, destination):
    payload = {"consulta": "SSD de prueba"} if old == "solicitar_inventario" else {"motivo": "Evaluar"}
    legacy = messages(old, payload)
    current = messages(new, english(payload))
    before = deepcopy((legacy, current))
    for batch in (legacy, current):
        assert handoffs.HANDOFF_TOOLS[batch[-1].name] == destination
        assert handoffs.selected_handoff(batch) is batch[-1]
        assert handoffs.handoff_reason(batch) == ("Consultar inventario" if old == "solicitar_inventario" else "Evaluar")
    assert handoffs.progress_token({"messages": legacy}) == handoffs.progress_token({"messages": current})
    assert (legacy, current) == before


@pytest.mark.parametrize("with_evidence,expected", [
    (False, "0572b05f25235ea30c8abe0cca7253e898f15b115a3fbfe1d5ae5067b5c12a21"),
    (True, "16dd48360061741d640a80e33412959a517f0b04be8fa32aa168e1465a1fe8ab"),
])
def test_frozen_legacy_tokens_are_unchanged(with_evidence, expected):
    history = [HumanMessage(content="Consulta")]+[
        ToolMessage(content="TRANSFERIR: Motivo", name=old, tool_call_id=str(i)) for i, (old, _, _) in enumerate(PAIRS)]
    if with_evidence:
        history.append(ToolMessage(content='{"hypothesis":"preliminar"}', name="diagnose_issue", tool_call_id="evidence"))
    assert handoffs.progress_token(dict(messages=history, request_revision=2)) == expected


@pytest.mark.parametrize("name", ["solicitar_inventario", "request_inventory"])
@pytest.mark.parametrize("with_args", [False, True])
@pytest.mark.parametrize("query", ["SSD", " "])
def test_inventory_request_preserves_special_reason(name, with_args, query):
    payload = {"consulta" if name == "solicitar_inventario" else "query": query}
    assert handoffs.handoff_reason(messages(name, payload, with_args=with_args)) == ("Consultar inventario" if query.strip() else None)


@pytest.mark.parametrize("first,failed", [("transferir_a_ventas", False), ("transfer_to_sales", False),
                                        ("transferir_a_ventas", True), ("transfer_to_sales", True)])
def test_mixed_batch_keeps_first_successful_result_and_matching_call(first, failed):
    second = "transferir_a_tecnico" if first.startswith("transfer_to_") else "transfer_to_hardware"
    a = messages(first, {"reason": "Primero"}, "a")
    b = messages(second, {"motivo": "Segundo"}, "b")
    if failed:
        a[-1].status = "error"
    batch = [AIMessage(content="", tool_calls=a[0].tool_calls+b[0].tool_calls), a[-1], b[-1]]
    before = deepcopy(batch)
    assert handoffs.selected_handoff(batch) is (b[-1] if failed else a[-1])
    assert handoffs.handoff_reason(batch) == ("Segundo" if failed else "Primero")
    assert batch == before
    assert handoffs.selected_handoff([*batch, HumanMessage(content="Otro turno")]) is None


@pytest.mark.parametrize("progress", [False, True])
def test_alias_cannot_bypass_historical_cycle_record_but_new_evidence_can(progress):
    original = dict(messages=[HumanMessage(content="Consulta"), *messages("transferir_a_ventas", {"motivo": "Evaluar"})], request_revision=2)
    token = handoffs.progress_token(original)
    historical = dict(origen="soporte", destino="ventas", motivo="Evaluar", request_revision=2,
                      progress_token=token, metadata={"source": "old-checkpoint"})
    resumed = {**original, "messages": [HumanMessage(content="Consulta"), *messages("transfer_to_sales", {"reason": "Otro motivo"})],
               "handoff_records": [historical]}
    if progress:
        resumed["messages"].append(HumanMessage(content="Nueva evidencia confirmada"))
        assert handoffs.make_handoff_record(resumed, "soporte", "ventas", "Evaluar", handoffs.ALLOWED_HANDOFFS)["progress_token"] != token
    else:
        assert policy.is_handoff_without_progress(resumed, "soporte", "ventas") is True
        with pytest.raises(ValueError, match="repetida"):
            handoffs.make_handoff_record(resumed, "soporte", "ventas", "Evaluar", handoffs.ALLOWED_HANDOFFS)
    assert historical["progress_token"] == token and historical["metadata"] == {"source": "old-checkpoint"}


AUDITS = [
    ("soporte", "transferir_a_tecnico", {"motivo": "Evaluar"}, "tecnico"),
    ("soporte", "transferir_a_software", {"motivo": "Evaluar"}, "software"),
    ("soporte", "transferir_a_ventas", {"motivo": "Evaluar"}, "ventas"),
    ("soporte", "transferir_a_facturacion", {"motivo": "Evaluar"}, "facturacion"),
    ("soporte", "transferir_a_logistica", {"motivo": "Evaluar"}, "logistica"),
    ("soporte", "transferir_a_garantia", {"motivo": "Evaluar"}, "garantia"),
    ("tecnico", "transferir_a_soporte", {"motivo": "Evaluar"}, "soporte"),
    ("tecnico", "transferir_a_ventas", {"motivo": "Cotizar", "alcance": "solo_servicio"}, "ventas"),
    ("tecnico", "transferir_a_ventas", {"motivo": "Cotizar", "alcance": "repuestos", "nombre_repuesto": "SSD de prueba", "cantidad": 1}, "almacen"),
    ("tecnico", "transferir_a_almacen", {"motivo": "Verificar", "accion": "TRANSFERIR_ALMACEN", "nombre_repuesto": "SSD de prueba", "cantidad": 1}, "almacen"),
    ("ventas", "solicitar_inventario", {"accion": "CONSULTAR_DISPONIBILIDAD", "consulta": "SSD de prueba"}, "almacen"),
]


@pytest.mark.parametrize("origin,name,payload,destination", AUDITS)
def test_graph_aliases_preserve_records_history_count_and_metadata(network, origin, name, payload, destination):
    module, _ = network
    base = dict(request_revision=2, handoff_count=1,
        handoff_history=[dict(origen="ventas", destino="tecnico", metadata={"id": "old"})],
        handoff_records=[dict(origen="ventas", destino="tecnico", motivo="Previo", request_revision=1,
                             progress_token="old-token", metadata={"id": "old"})])
    outputs = []
    for tool_name, data in [(name, payload), (ALIASES[name], english(payload))]:
        state = {**deepcopy(base), "messages": [HumanMessage(content="Confirmo SSD de prueba"), *messages(tool_name, data)]}
        before = deepcopy(state)
        result = module.record_handoff(state, origin)
        assert module.detect_handoff(state["messages"]) == handoffs.HANDOFF_TOOLS[tool_name]
        assert result["next_agent"] == destination and result["handoff_count"] == 2
        assert result["handoff_history"] == [base["handoff_history"][0], dict(origin=origin, destination=destination)]
        assert result["handoff_records"][0] == base["handoff_records"][0]
        assert state == before
        outputs.append(result)
    assert outputs[0] == outputs[1]


@pytest.mark.parametrize("name", ["transferir_a_ventas", "transfer_to_sales"])
@pytest.mark.parametrize("valid", [False, True])
def test_software_commercial_audit_keeps_current_guard(network, name, valid):
    module, _ = network
    state = dict(messages=[HumanMessage(content="Confirmo Evaluación del editor. Cotiza solo servicio sin repuestos"),
        *messages(name, {"reason": "Evaluar", "scope": "solo_servicio"})], request_revision=2)
    if valid:
        state["technical_assessment"] = {"software_diagnosis": "Evaluación del editor"}
    result = module.record_handoff(state, "software")
    assert result["next_agent"] == ("ventas" if valid else "finalizar")
    assert (result.get("quote_scope") == "solo_servicio") is valid
    assert bool(result.get("handoff_records")) is valid


@pytest.mark.parametrize("english_name", [False, True])
@pytest.mark.parametrize("kind", ["unknown_scope", "bad_part", "empty_query", "stale_inventory", "no_shortage", "conflict"])
def test_invalid_handoffs_remain_blocked(network, english_name, kind):
    module, _ = network
    origin, name, data = "tecnico", "transferir_a_ventas", {"motivo": "Evaluar", "alcance": "sin_determinar"}
    if kind == "bad_part":
        name, data = "transferir_a_almacen", {"motivo": "Evaluar", "accion": "TRANSFERIR_ALMACEN", "nombre_repuesto": "SSD", "cantidad": True}
    elif kind == "empty_query":
        origin, name, data = "ventas", "solicitar_inventario", {"consulta": " "}
    elif kind in {"stale_inventory", "no_shortage"}:
        origin, data = ("almacen" if kind == "stale_inventory" else "compras"), {"motivo": "Evaluar"}
    elif kind == "conflict":
        origin, data = "soporte", {"motivo": "Evaluar", "reason": "Otra cosa"}
    if english_name:
        name = ALIASES[name]
        data = english(data) if kind != "conflict" else data
    state = dict(messages=[HumanMessage(content="SSD"), *messages(name, data)], request_revision=2, inventory_revision=1)
    result = module.record_handoff(state, origin)
    assert result["next_agent"] == "finalizar"
    assert not result.get("handoff_history") and not result.get("handoff_records")
    assert "quote_scope" not in result


def test_active_tools_nodes_limits_and_policy_producer_are_unchanged(network):
    module, _ = network
    aliases = set(ALIASES.values())
    assert module.MAX_HANDOFFS == 5 and module.MAX_TOOL_ITERATIONS == 6
    assert set(module.AGENT_NODES) == set(handoffs.ALLOWED_HANDOFFS)
    graph = module.build_graph().get_graph()
    migrated = {
        "soporte": {"transfer_to_warranty", "transfer_to_logistics", "transfer_to_billing",
                    "transfer_to_hardware", "transfer_to_sales", "transfer_to_software"},
        "tecnico": {"transfer_to_support", "transfer_to_software", "transfer_to_sales", "transfer_to_warehouse", "transfer_to_logistics"},
        "compras": {"transfer_to_sales"},
        "almacen": {"transfer_to_sales", "transfer_to_purchasing"},
        "ventas": {"request_inventory", "transfer_to_support", "transfer_to_hardware", "transfer_to_billing"},
        "facturacion": {"transfer_to_support", "transfer_to_sales", "transfer_to_logistics"},
        "logistica": {"transfer_to_support"},
        "garantia": {"transfer_to_support", "transfer_to_logistics"},
        "software": {"transfer_to_support", "transfer_to_hardware", "transfer_to_sales", "transfer_to_logistics"},
    }
    for role in module.AGENT_NODES:
        active = getattr(module, f"{role}_tools")
        assert aliases & {tool.name for tool in active} == migrated.get(role, set())
        assert aliases & set(graph.nodes[f"{role}_tools"].data.tools_by_name) == migrated.get(role, set())
    pending = policy.handoff("soporte", "transferir_a_tecnico", motivo="Evaluar")
    assert pending["messages"][0].tool_calls[0]["name"] == "transferir_a_tecnico"
    assert pending["messages"][0].tool_calls[0]["args"] == {"motivo": "Evaluar"}


@pytest.mark.parametrize("name", ["transferir_a_soporte", "transfer_to_support"])
def test_support_return_reader_prevents_old_symptom_rerouting(network, name):
    module, _ = network
    state = dict(messages=[HumanMessage(content="Mi PC no enciende"), ToolMessage(content="Orientación", name=name, tool_call_id="return")])
    result = module.soporte_node(state)
    assert not result["messages"][0].tool_calls
    assert "consulta quieres continuar" in result["messages"][0].content


@pytest.mark.parametrize("role,old,new", [("ventas", "transferir_a_tecnico", "transfer_to_hardware"),
    ("ventas", "transferir_a_soporte", "transfer_to_support"), ("almacen", "transferir_a_ventas", "transfer_to_sales")])
def test_context_readers_keep_original_call_result_pairs(network, role, old, new):
    module, _ = network
    agent_module = sys.modules[f"app.agents.decentralized.{role}"]
    build = agent_module.build_sales_context if role == "ventas" else agent_module.build_warehouse_context
    for name in (old, new):
        batch = messages(name, {"reason": "Evaluar"})
        state = {"messages": batch}
        before = deepcopy(state)
        assert build(state)[:2] == batch and state == before


def test_warehouse_incoming_part_reader_accepts_alias_without_rewriting(network):
    _, _ = network
    warehouse = sys.modules["app.agents.decentralized.almacen"]
    payload = {"accion": "TRANSFERIR_ALMACEN", "nombre_repuesto": "SSD", "cantidad": 1}
    old = messages("transferir_a_almacen", payload)[-1]
    new = messages("transfer_to_warehouse", payload)[-1]
    assert warehouse.build_warehouse_context({"messages": [old]}) == warehouse.build_warehouse_context({"messages": [new]})


@pytest.mark.parametrize("name", ["transferir_a_ventas", "transfer_to_sales"])
def test_sales_preserves_incoming_software_pair_and_current_record(network, name):
    _, _ = network
    sales = sys.modules["app.agents.decentralized.ventas"]
    batch = messages(name, {"reason": "Evaluar", "scope": "solo_servicio"})
    state = dict(messages=batch, request_revision=2, handoff_records=[dict(
        origin="software", destination="ventas", reason="Evaluar", request_revision=2,
        progress_token="stored", metadata={"source": "checkpoint"})])
    before = deepcopy(state)
    context = sales.build_sales_context(state)
    assert context[:2] == batch and "Evaluar" in context[-1].content
    assert state == before


@pytest.mark.parametrize("origin,name,unavailable", [
    ("compras", "transfer_to_support", False), ("soporte", "transfer_to_support", False),
    ("unknown", "transfer_to_hardware", False), ("soporte", "transfer_to_hardware", True),
])
def test_alias_does_not_expand_matrix_or_bypass_agent_availability(network, monkeypatch, origin, name, unavailable):
    module, _ = network
    if unavailable:
        monkeypatch.delitem(module.AGENT_NODES, "tecnico")
    result = module.record_handoff(dict(messages=messages(name, {"reason": "Evaluar"})), origin)
    assert result["next_agent"] == "finalizar"
    assert not result.get("handoff_history") and not result.get("handoff_records")


@pytest.mark.parametrize("limit", ["handoffs", "tools"])
def test_alias_preserves_existing_limits(network, limit):
    module, _ = network
    state = dict(messages=messages("transfer_to_hardware", {"reason": "Evaluar"}))
    state.update({"handoff_count": 5} if limit == "handoffs" else {"tool_iterations": {"soporte": 5}})
    result = module.record_handoff(state, "soporte")
    assert result["next_agent"] == "finalizar" and "Límite" in result["errors"][-1]
    assert not result.get("handoff_records")


@pytest.mark.parametrize("mode", ["valid", "no_reason", "no_service"])
def test_future_software_reader_uses_english_reason_and_commercial_guard(agent, monkeypatch, mode):
    module, regular, _, _ = agent
    def future(reason: str, scope: Literal["solo_servicio"]) -> dict:
        return {"reason": reason, "scope": scope}
    tool = StructuredTool.from_function(future, name="transfer_to_sales", description="Test-only future tool")
    monkeypatch.setattr(module, "software_tools", [*module.software_tools, tool])
    regular.response = AIMessage(content="", tool_calls=[dict(name=tool.name,
        args=dict(reason=" " if mode == "no_reason" else "Evaluar", scope="solo_servicio"), id="future")])
    state = software_state("Confirmo Evaluación del editor. Cotiza solo servicio sin repuestos", request_revision=2)
    if mode != "no_service":
        state["technical_assessment"] = {"software_diagnosis": "Evaluación del editor"}
    before = deepcopy(state)
    result = module.software_node(state)
    assert bool(result["messages"][0].tool_calls) is (mode == "valid")
    assert state == before


def test_software_does_not_activate_an_unregistered_english_tool(agent):
    module, regular, _, _ = agent
    regular.response = AIMessage(content="", tool_calls=[dict(name="transfer_to_purchasing", args={"reason": "Evaluar"}, id="future")])
    assert not module.software_node(software_state("La aplicación se cierra"))["messages"][0].tool_calls


@pytest.mark.parametrize("origin,name,args", [
    ("soporte", "transferir_a_tecnico", {"motivo": "Evaluar"}),
    ("tecnico", "transferir_a_almacen", {"motivo": "Verificar", "nombre_repuesto": "SSD de prueba", "cantidad": 1}),
    ("software", "transferir_a_ventas", {"motivo": "Evaluación del editor", "alcance": "solo_servicio"}),
])
def test_pending_legacy_checkpoint_resumes_without_turn_preparation(network, monkeypatch, origin, name, args):
    module, controls = network
    def forbidden(state):
        pytest.fail("Turn preparation must not run on this resume")
    monkeypatch.setattr(module, "prepare_turn", forbidden)
    saver = MemorySaver()
    config = {"configurable": {"thread_id": "pending-legacy"}}
    event = AIMessage(content="", tool_calls=[dict(name=name, args=args, id="pending")], id="event")
    before = deepcopy(event)
    state = dict(messages=[HumanMessage(content="Confirmo Evaluación del editor. Cotiza solo servicio sin repuestos; SSD de prueba", id="user"), event],
        current_agent=origin, request_revision=2, handoff_count=0, handoff_history=[], handoff_records=[],
        technical_assessment={"software_diagnosis": "Evaluación del editor"})
    graph = module.build_graph(checkpointer=saver)
    graph.update_state(config, state, as_node=origin)
    result = module.build_graph(checkpointer=saver).invoke(None, config)
    matches = [message for message in result["messages"] if isinstance(message, ToolMessage) and message.tool_call_id == "pending"]
    assert len(matches) == 1 and matches[0].name == name and matches[0].status != "error"
    assert event == before
    assert result["handoff_count"] == len(result["handoff_history"]) == len(result["handoff_records"])
    assert len(controls["inventory_calls"]) == (1 if name == "transferir_a_almacen" else 0)
