"""Real readers and graph; external services replaced by the existing fixture."""
from copy import deepcopy
import json
import sys
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver

from app.agents.decentralized import handoffs, policy
from app.agents.decentralized.data_compat import DataCompatibilityError
from test_software_e2e import network


KEYS = {"origen": "origin", "destino": "destination", "motivo": "reason",
        "accion": "action", "alcance": "scope", "nombre_repuesto": "part_name",
        "cantidad": "quantity", "consulta": "query", "nombre": "name",
        "precio_unitario": "unit_price", "disponible": "available", "encontrado": "found"}
FORMATS = ["legacy", "english", "mixed"]


def encoded(data, style):
    english = {KEYS.get(key, key): value for key, value in data.items()}
    return deepcopy(data if style == "legacy" else english if style == "english"
                    else {**data, **english})


def inventory_row():
    return {"requested_name": "SSD de prueba", "name": "SSD de prueba", "quantity": 1,
            "stock": 3, "unit_price": "180.00", "available": True, "found": True,
            "tool_call_id": "inventory-1"}


def business_state():
    return {"messages": [HumanMessage(content="Consulta")], "request_revision": 2,
            "required_parts": [{"name": "SSD de prueba", "quantity": 1}],
            "inventory_results": [inventory_row()], "inventory_revision": 2,
            "inventory_pending": False}


def transfer_messages(payload, args=None, name="transferir_a_ventas"):
    messages = [] if args is None else [AIMessage(content="", tool_calls=[
        {"name": name, "args": args, "id": "transfer-1"}])]
    return [*messages, ToolMessage(content=json.dumps(payload), name=name, tool_call_id="transfer-1")]


@pytest.mark.parametrize("style", FORMATS)
@pytest.mark.parametrize("with_args", [False, True])
def test_reason_reads_formats_without_changing_messages(style, with_args):
    payload = encoded({"motivo": "Cotizar servicio", "alcance": "solo_servicio"}, style)
    messages = transfer_messages(payload, payload if with_args else None)
    before = deepcopy(messages)
    assert handoffs.handoff_reason(messages) == "Cotizar servicio"
    assert messages == before


@pytest.mark.parametrize("location", ["args", "result"])
@pytest.mark.parametrize("legacy,canonical,left,right", [
    ("motivo", "reason", "first", "second"),
    ("alcance", "scope", "solo_servicio", "repuestos"),
    ("cantidad", "quantity", True, 1),
    ("nombre_repuesto", "part_name", "SSD", "RAM"),
    ("accion", "action", "TRANSFERIR_ALMACEN", "SOLICITAR_COTIZACION"),
    ("consulta", "query", "SSD", "RAM"),
])
def test_conflicting_args_or_result_cannot_supply_a_reason(location, legacy, canonical, left, right):
    conflict = {"motivo": "Cotizar", legacy: left, canonical: right}
    good = {"motivo": "Cotizar"}
    messages = transfer_messages(conflict if location == "result" else good,
                                 conflict if location == "args" else good)
    before = deepcopy(messages)
    assert handoffs.handoff_reason(messages) is None
    assert messages == before


def test_selected_transfer_remains_the_first_successful_call():
    messages = [ToolMessage(content='{"reason":"Primera"}', name="transferir_a_ventas", tool_call_id="first"),
                ToolMessage(content='{"motivo":"Segunda"}', name="transferir_a_tecnico", tool_call_id="second")]
    assert handoffs.selected_handoff(messages) is messages[0]
    assert handoffs.handoff_reason(messages) == "Primera"


@pytest.mark.parametrize("style", FORMATS)
@pytest.mark.parametrize("query", ["SSD de prueba", " "])
def test_inventory_query_reason_with_matched_call(style, query):
    payload = encoded({"consulta": query}, style)
    messages = transfer_messages(payload, payload, name="solicitar_inventario")
    assert handoffs.handoff_reason(messages) == ("Consultar inventario" if query.strip() else None)


@pytest.mark.parametrize("content,expected", [
    ("TRANSFERIR_VENTAS: Revisar", "Revisar"), ("Revisar", "Revisar"),
    ("null", None), ('"Revisar"', None), ("[]", None),
])
def test_legacy_text_and_unstructured_json_keep_existing_behavior(content, expected):
    message = ToolMessage(content=content, name="transferir_a_ventas", tool_call_id="legacy")
    assert handoffs.handoff_reason([message]) == expected


@pytest.mark.parametrize("style", FORMATS)
def test_progress_token_cycles_and_legitimate_return_are_unchanged(style):
    state = business_state()
    token = handoffs.progress_token(state)
    assert token == "18c82dd2f91efb10ecd99747995d7176aa331e3146a378ff9657da87bcd1ebce"
    record = handoffs.make_handoff_record(state, "ventas", "tecnico", "Compatibilidad", set(handoffs.ALLOWED_HANDOFFS))
    assert set(record) == {"origin", "destination", "reason", "request_revision", "progress_token"}
    legacy = {"origen": record["origin"], "destino": record["destination"],
              "motivo": record["reason"], "request_revision": record["request_revision"],
              "progress_token": record["progress_token"], "metadata": {"source": "old-checkpoint"}}
    state["handoff_records"] = [encoded(legacy, style)]
    before = deepcopy(state)
    assert handoffs.progress_token(state) == token
    assert policy.is_handoff_without_progress(state, "ventas", "tecnico") is True
    with pytest.raises(ValueError, match="repetida"):
        handoffs.make_handoff_record(state, "ventas", "tecnico", "Otro motivo", set(handoffs.ALLOWED_HANDOFFS))
    returned = handoffs.make_handoff_record(state, "tecnico", "ventas", "Volver", set(handoffs.ALLOWED_HANDOFFS))
    assert returned["destination"] == "ventas"
    assert state == before
    state["messages"].append(ToolMessage(content="Nueva evidencia", name="consultar_documentacion", tool_call_id="new"))
    assert not policy.is_handoff_without_progress(state, "ventas", "tecnico")


def test_conflicting_records_fail_closed_even_after_an_earlier_match():
    state = business_state()
    record = handoffs.make_handoff_record(state, "ventas", "tecnico", "Evaluar", set(handoffs.ALLOWED_HANDOFFS))
    state["handoff_records"] = [record, {**record, "destino": "software"}]
    assert policy.is_handoff_without_progress(state, "ventas", "tecnico") is True
    with pytest.raises(DataCompatibilityError):
        handoffs.make_handoff_record(state, "tecnico", "ventas", "Volver", set(handoffs.ALLOWED_HANDOFFS))


@pytest.mark.parametrize("origin,destination", [
    ("soporte", "tecnico"), ("software", "ventas"), ("garantia", "logistica"),
])
def test_new_record_contract_is_english_only(origin, destination):
    state = business_state()
    before = deepcopy(state)
    record = handoffs.make_handoff_record(state, origin, destination, "  Evaluar  ",
                                         set(handoffs.ALLOWED_HANDOFFS))
    assert record == {"origin": origin, "destination": destination, "reason": "Evaluar",
                      "request_revision": 2, "progress_token": handoffs.progress_token(state)}
    assert set(handoffs.HandoffRecord.__annotations__) == set(record)
    assert state == before


@pytest.mark.parametrize("style", FORMATS)
def test_cli_diagnostic_accepts_historical_and_new_history(capsys, style):
    from probar_chat import mostrar_diagnostico
    state = {"handoff_history": [encoded({"origen": "soporte", "destino": "tecnico",
                                        "metadata": {"source": "checkpoint"}}, style)]}
    before = deepcopy(state)
    mostrar_diagnostico(state)
    output = capsys.readouterr().out
    assert "Transferencia:" in output and "soporte" in output and "tecnico" in output
    assert state == before


@pytest.mark.parametrize("entry", [
    {"origen": "soporte", "origin": "ventas", "destino": "tecnico"},
    {"origen": "soporte", "destino": "tecnico", "destination": "ventas"},
])
def test_cli_diagnostic_rejects_conflicting_history(capsys, entry):
    from probar_chat import mostrar_diagnostico
    mostrar_diagnostico({"handoff_history": [entry]})
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize("style", FORMATS)
@pytest.mark.parametrize("origin,name,payload,destination", [
    ("tecnico", "transferir_a_ventas", {"motivo": "Revisar", "alcance": "solo_servicio"}, "ventas"),
    ("tecnico", "transferir_a_ventas", {"motivo": "Repuesto", "alcance": "repuestos",
     "nombre_repuesto": "SSD de prueba", "cantidad": 1}, "almacen"),
    ("tecnico", "transferir_a_almacen", {"motivo": "Consultar", "accion": "TRANSFERIR_ALMACEN",
     "nombre_repuesto": "SSD de prueba", "cantidad": 1}, "almacen"),
    ("ventas", "solicitar_inventario", {"accion": "CONSULTAR_DISPONIBILIDAD", "consulta": "SSD de prueba"}, "almacen"),
])
def test_graph_payload_readers_and_english_producers(network, style, origin, name, payload, destination):
    module, _ = network
    state = {"messages": [HumanMessage(content="Confirmo SSD de prueba"),
                          *transfer_messages(encoded(payload, style), name=name)], "request_revision": 0}
    before = deepcopy(state)
    result = module.record_handoff(state, origin)
    assert result["next_agent"] == destination
    assert result["handoff_history"] == [{"origin": origin, "destination": destination}]
    assert set(result["handoff_records"][0]) == {"origin", "destination", "reason", "request_revision", "progress_token"}
    if name == "solicitar_inventario":
        assert result["inventory_query"] == "SSD de prueba"
    if payload.get("nombre_repuesto"):
        assert result["required_parts"] == [{"name": "SSD de prueba", "quantity": 1}]
    assert state == before


@pytest.mark.parametrize("location", ["payload", "history", "records"])
def test_graph_conflicts_do_not_append_records_or_enable_a_transfer(network, location):
    module, _ = network
    state = {"messages": transfer_messages({"motivo": "Cotizar", "alcance": "solo_servicio"}),
             "request_revision": 0}
    if location == "payload":
        state["messages"] = transfer_messages({"motivo": "Cotizar", "reason": "Otro motivo"})
    elif location == "history":
        state["handoff_history"] = [{"origen": "soporte", "origin": "software", "destino": "tecnico"}]
    else:
        state["handoff_records"] = [{"origen": "soporte", "origin": "software", "destino": "tecnico"}]
    before = deepcopy(state)
    result = module.record_handoff(state, "tecnico")
    assert result["next_agent"] == "finalizar" and result["errors"]
    assert not any(key in result for key in ("quote_scope", "handoff_history", "handoff_records", "required_parts"))
    assert state == before


def test_history_order_count_and_metadata_survive_a_valid_append(network):
    module, _ = network
    history = [encoded({"origen": origin, "destino": destination,
                        "metadata": {"position": index}}, style)
               for index, (style, origin, destination) in enumerate([
                   ("legacy", "soporte", "tecnico"), ("english", "tecnico", "software"),
                   ("mixed", "software", "tecnico")])]
    state = {"messages": transfer_messages({"motivo": "Cotizar", "alcance": "solo_servicio"}),
             "handoff_history": history, "handoff_count": len(history)}
    before = deepcopy(state)
    result = module.record_handoff(state, "tecnico")
    assert result["handoff_history"] == [*before["handoff_history"], {"origin": "tecnico", "destination": "ventas"}]
    assert result["handoff_count"] == 4
    assert state == before


@pytest.mark.parametrize("style", FORMATS)
def test_software_scope_reader_keeps_commercial_guard(network, style):
    module, _ = network
    payload = encoded({"motivo": "Evaluar editor", "alcance": "solo_servicio"}, style)
    state = {"messages": [HumanMessage(content="Confirmo Reconfigurar editor; cotiza solo servicio sin repuestos"),
                          *transfer_messages(payload)], "request_revision": 0,
             "technical_assessment": {"software_diagnosis": "Reconfigurar editor"}}
    accepted = module.record_handoff(state, "software")
    assert accepted["next_agent"] == "ventas" and accepted["quote_scope"] == "solo_servicio"
    rejected = module.record_handoff({**state, "request_revision": None}, "software")
    assert rejected["next_agent"] == "finalizar" and "quote_scope" not in rejected


@pytest.mark.parametrize("style", FORMATS)
def test_sales_inventory_formats_produce_the_same_quote_and_response(style):
    row = {"nombre": "SSD de prueba", "cantidad": 2, "stock": 3,
           "precio_unitario": "180.00", "disponible": True, "encontrado": True,
           "metadata": {"source": "fixture"}}
    source = [encoded(row, style)]
    before = deepcopy(source)
    result = policy.build_verified_quote(source, [])
    assert result == policy.build_verified_quote([row], [])
    assert result[0]["known_parts_subtotal"] == "360.00"
    assert result[0]["total"] is None
    assert source == before


def test_sales_inventory_mixed_list_deduplicates_and_conflicts_block_totals():
    row = {"nombre": "SSD de prueba", "cantidad": 1, "stock": 3,
           "precio_unitario": "180.00", "disponible": True}
    quote, _ = policy.build_verified_quote([row, encoded(row, "english")], [])
    assert len(quote["parts"]) == 1 and quote["known_parts_subtotal"] == "180.00"
    quote, reply = policy.build_verified_quote([row, {**row, "quantity": True}], [])
    assert quote["parts"] == [] and quote["known_parts_subtotal"] is None
    assert "No puedo confirmar" in reply


@pytest.mark.parametrize("style", FORMATS)
def test_sales_context_preserves_pairs_and_reads_current_handoff(network, style):
    module = sys.modules["app.agents.decentralized.ventas"]
    messages = transfer_messages({"motivo": "Evaluar editor"}, {"motivo": "Evaluar editor"})
    state = {"messages": messages, "request_revision": 2,
             "handoff_records": [encoded({"origen": "software", "destino": "ventas", "motivo": "Evaluar editor",
                 "request_revision": 2, "progress_token": "old", "metadata": [1]}, style)]}
    before = deepcopy(state)
    context = module.build_sales_context(state)
    assert context[:2] == messages
    assert "Evaluar editor" in context[-1].content
    assert state == before


def test_sales_rejects_conflicts_before_model_or_deterministic_handoffs(network):
    module = sys.modules["app.agents.decentralized.ventas"]
    state = {"messages": [HumanMessage(content="Consulta stock SSD")],
             "handoff_records": [{"destino": "ventas", "destination": "tecnico"}]}
    before = deepcopy(state)
    result = module.ventas_node(state)
    assert result["errors"] and not result["messages"][0].tool_calls
    assert "quote" not in result
    assert state == before


def test_raw_inventory_readers_preserve_english_data_and_sales_output(network):
    module = sys.modules["app.agents.decentralized.ventas"]
    state = business_state()
    state["inventory_results"][0]["metadata"] = {"nombre": "external", "origen": "fixture"}
    before = deepcopy(state)
    assert policy.current_inventory_results(state) == state["inventory_results"]
    sales, errors = module.validate_inventory(state)
    assert not errors
    assert sales[0]["name"] == "SSD de prueba" and sales[0]["unit_price"] == "180.00"
    assert not {"encontrado", "nombre", "cantidad", "precio_unitario", "disponible"}.intersection(sales[0])
    assert policy.evaluate_supply(state)["destination"] == "ventas"
    patch = network[0].guardar_inventario({**state, "messages": [ToolMessage(
        content=json.dumps(state["inventory_results"][0]), name="consultar_inventario", tool_call_id="inventory-1")]})
    assert patch["inventory_results"] == state["inventory_results"]
    assert state == before
    state["inventory_revision"] = 1
    assert policy.current_inventory_results(state) == []


@pytest.mark.parametrize("style", FORMATS)
@pytest.mark.parametrize("quantity,stock,found,match_status,price,subtotal,known,part_count", [
    (2, 3, True, "exact", "180.10", "360.20", "360.20", 1),
    (1, 0, True, "exact", "180.00", None, "0.00", 1),
    (2, 1, True, "exact", "180.00", None, "0.00", 1),
    (1, 0, False, "not_found", "0.00", None, None, 0),
    (1, 0, False, "ambiguous", "0.00", None, None, 0),
    (3, 3, True, "exact", "0.10", "0.30", "0.30", 1),
])
def test_sales_projection_english_contract_and_legacy_quote_equivalence(
    network, style, quantity, stock, found, match_status, price, subtotal, known, part_count,
):
    module = sys.modules["app.agents.decentralized.ventas"]
    raw = {**inventory_row(), "quantity": quantity, "stock": stock, "unit_price": price,
           "available": stock >= quantity, "found": found, "match_status": match_status,
           "metadata": {"source": "fixture", "nombre": "unchanged"}}
    state = {"inventory_results": [raw]}
    before = deepcopy(state)
    items, errors = module.validate_inventory(state)
    assert errors == []
    assert items == [{"found": found, "name": raw["name"], "quantity": quantity,
                      "stock": stock, "unit_price": price, "available": stock >= quantity,
                      "subtotal": subtotal}]
    legacy = {"encontrado": found, "nombre": raw["name"], "cantidad": quantity,
              "stock": stock, "precio_unitario": price, "disponible": stock >= quantity,
              "subtotal": subtotal}
    formatted = [encoded(legacy, style)]
    formatted_before = deepcopy(formatted)
    produced = policy.build_verified_quote(items, [])
    assert produced == policy.build_verified_quote(formatted, [])
    quote, _ = produced
    assert quote["known_parts_subtotal"] == known
    assert len(quote["parts"]) == part_count
    assert quote["total"] is None and quote["labor_total"] is None
    assert json.loads(module.build_inventory_context(state).content.split("\n")[1]) == items
    assert state == before and formatted == formatted_before


@pytest.mark.parametrize("legacy,canonical,conflicting", [
    ("encontrado", "found", False), ("nombre", "name", "Otra referencia"),
    ("cantidad", "quantity", True), ("precio_unitario", "unit_price", 180.0),
    ("disponible", "available", False),
])
def test_sales_projection_conflicts_block_all_quote_parts(network, legacy, canonical, conflicting):
    module = sys.modules["app.agents.decentralized.ventas"]
    items, errors = module.validate_inventory({"inventory_results": [inventory_row()]})
    assert errors == [] and canonical in items[0]
    broken = {**items[0], legacy: conflicting}
    source = [items[0], broken]
    before = deepcopy(source)
    quote, reply = policy.build_verified_quote(source, [])
    assert quote["parts"] == []
    assert quote["known_parts_subtotal"] is None and quote["total"] is None
    assert "No puedo confirmar" in reply
    assert source == before


def test_stale_inventory_stays_blocked_at_the_existing_handoff_guard(network):
    module, _ = network
    state = {**business_state(), "inventory_revision": 1}
    state["messages"] += transfer_messages({"motivo": "Inventario verificado"})
    before = deepcopy(state)
    assert policy.current_inventory_results(state) == []
    prepared = policy.prepare_inventory_request(state, state["required_parts"])
    assert prepared["inventory_results"] == [] and prepared["inventory_pending"] is True
    result = module.record_handoff(state, "almacen")
    assert result["next_agent"] == "finalizar" and result["errors"]
    assert not any(key in result for key in ("quote", "quote_scope", "handoff_records"))
    assert state == before


@pytest.mark.parametrize("style", FORMATS)
@pytest.mark.parametrize("mode", ["legitimate", "repeat", "conflict"])
def test_paused_checkpoint_resumes_through_readers_without_preparation(network, monkeypatch, style, mode):
    module, _ = network
    saver, repo = MemorySaver(), MagicMock()
    original_compile = module.StateGraph.compile
    original_prepare = module.preparar_turno
    prepared = []

    def compile_with_audit_pause(builder, *args, **kwargs):
        kwargs["interrupt_before"] = [*kwargs.get("interrupt_before", []), "auditar_tecnico"]
        return original_compile(builder, *args, **kwargs)

    def prepare(state):
        prepared.append(True)
        return original_prepare(state)

    monkeypatch.setattr(module.StateGraph, "compile", compile_with_audit_pause)
    monkeypatch.setattr(module, "preparar_turno", prepare)
    graph = module.build_graph(checkpointer=saver, financial_repository=repo)
    config = {"configurable": {"thread_id": f"compat-{style}-{mode}"}}
    graph.invoke({"messages": [HumanMessage(content="Cotiza un diagnostico")],
                  "current_agent": "tecnico", "request_revision": 0}, config)
    snapshot = graph.get_state(config)
    assert snapshot.next == ("auditar_tecnico",)
    token = handoffs.progress_token(snapshot.values)
    record = {"origen": "tecnico" if mode == "repeat" else "soporte",
              "destino": "ventas" if mode == "repeat" else "tecnico",
              "motivo": "Anterior", "request_revision": 0,
              "progress_token": token, "metadata": {"source": "checkpoint"}}
    record = encoded(record, style)
    if mode == "conflict":
        record.update(origen="soporte", origin="software")
    history = [encoded({"origen": "soporte", "destino": "tecnico", "metadata": [1]}, style)]
    graph.update_state(config, {"handoff_records": [record], "handoff_history": history,
                               "handoff_count": 1}, as_node="tecnico_tools")
    saved = deepcopy(graph.get_state(config).values)
    rebuilt = module.build_graph(checkpointer=saver, financial_repository=repo)
    result = rebuilt.invoke(None, config)
    assert len(prepared) == 1
    assert result["handoff_records"][0] == saved["handoff_records"][0]
    assert result["handoff_history"][0] == saved["handoff_history"][0]
    assert result["messages"][:len(saved["messages"])] == saved["messages"]
    assert repo.mock_calls == []
    if mode == "legitimate":
        assert result["current_agent"] == "ventas"
        assert len(result["handoff_history"]) == len(history) + 1
        assert result["handoff_history"][-1] == {"origin": "tecnico", "destination": "ventas"}
        assert "origin" in result["handoff_records"][-1]
        assert set(result["handoff_records"][-1]) == {
            "origin", "destination", "reason", "request_revision", "progress_token",
        }
        assert result["handoff_records"][-1]["progress_token"] == token
        assert rebuilt.get_state(config).values["handoff_records"] == result["handoff_records"]
    else:
        assert result["errors"] and result["next_agent"] == "finalizar"
        assert result["handoff_records"] == saved["handoff_records"]
        assert result["handoff_history"] == saved["handoff_history"]
        assert "quote_scope" not in result


@pytest.mark.parametrize("style", ["legacy", "mixed"])
def test_software_live_handoff_keeps_public_arguments_and_result(network, style):
    module, controls = network
    args = {"motivo": "Evaluar editor"}
    if style == "mixed":
        args["reason"] = "Evaluar editor"
    response = AIMessage(content="", tool_calls=[
        dict(name="transferir_a_tecnico", args=args, id="live-public-call"),
    ])
    original_calls = deepcopy(response.tool_calls)
    controls["handlers"]["software"] = lambda messages: response
    controls["handlers"]["tecnico"] = lambda messages: AIMessage(content="Evaluacion preliminar")
    value = {"messages": [HumanMessage(content="Consulta del editor", id="live-user")], "current_agent": "software"}
    before = deepcopy(value)
    result = module.graph.invoke(value)
    incoming = next(message for message in result["messages"] if isinstance(message, AIMessage) and message.tool_calls)
    output = next(message for message in result["messages"] if isinstance(message, ToolMessage))
    assert incoming.tool_calls == original_calls
    assert output.name == "transferir_a_tecnico" and output.tool_call_id == "live-public-call"
    assert output.content == "TRANSFERIR_TECNICO: Evaluar editor" and output.status == "success"
    assert result["handoff_history"] == [{"origin": "software", "destination": "tecnico"}]
    assert value == before


@pytest.mark.parametrize("style", FORMATS)
@pytest.mark.parametrize("mode", ["legitimate", "repeat", "contradiction"])
def test_software_payload_checkpoint_fixture_resumes_without_rewriting_messages(network, monkeypatch, style, mode):
    module, controls = network
    saver, repo = MemorySaver(), MagicMock()

    def forbidden(*args, **kwargs):
        pytest.fail("A tools-completed checkpoint must resume at the auditor")

    monkeypatch.setattr(module, "preparar_turno", forbidden)
    controls["handlers"]["software"] = forbidden
    controls["handlers"]["ventas"] = forbidden
    graph = module.build_graph(checkpointer=saver, financial_repository=repo)
    args = {"motivo": "Cotizar servicio", "alcance": "solo_servicio"}
    payload = encoded({**args, "accion": "SOLICITAR_COTIZACION", "nombre_repuesto": "", "cantidad": 1}, style)
    if mode == "contradiction":
        payload.update(motivo="Cotizar servicio", reason="Otro motivo")
    messages = [HumanMessage(content="Confirmo Servicio definido; cotiza solo servicio sin repuestos"),
                *transfer_messages(payload, args)]
    initial = {"messages": messages, "current_agent": "software", "customer_id": 10,
               "request_revision": 1, "technical_assessment": {"software_diagnosis": "Servicio definido"},
               "handoff_count": 1, "handoff_history": [{"origen": "soporte", "destino": "software", "metadata": [1]}]}
    token = handoffs.progress_token(initial)
    initial["handoff_records"] = [{"origen": "software" if mode == "repeat" else "soporte",
        "destino": "ventas" if mode == "repeat" else "software", "motivo": "Anterior",
        "request_revision": 1, "progress_token": token, "metadata": {"source": "fixture"}}]
    config = {"configurable": {"thread_id": f"software-payload-{style}-{mode}"}}
    graph.update_state(config, initial, as_node="software_tools")
    saved = graph.get_state(config)
    assert saved.next == ("auditar_software",)
    original = deepcopy(saved.values)
    rebuilt = module.build_graph(checkpointer=saver, financial_repository=repo)
    result = rebuilt.invoke(None, config, context={"authenticated_customer_id": 10})
    assert result["messages"][:len(original["messages"])] == original["messages"]
    assert result["handoff_records"][0] == original["handoff_records"][0]
    assert result["handoff_history"][0] == original["handoff_history"][0]
    assert result["messages"][2].content == json.dumps(payload)
    assert result["messages"][2].tool_call_id == "transfer-1"
    assert repo.mock_calls == []
    if mode == "legitimate":
        assert result["current_agent"] == "ventas" and result["quote_scope"] == "solo_servicio"
        assert result["handoff_count"] == 2 and len(result["handoff_records"]) == 2
        assert result["handoff_records"][-1]["progress_token"] == token
        assert result["quote"]["total"] is None
    else:
        assert result["next_agent"] == "finalizar" and result["errors"]
        assert result["handoff_count"] == 1
        assert result["handoff_records"] == original["handoff_records"]
        assert result["handoff_history"] == original["handoff_history"]
        assert "quote" not in result and "quote_scope" not in result
