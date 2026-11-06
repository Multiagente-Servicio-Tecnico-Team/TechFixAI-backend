"""Validación local de rutas, sin clientes ni servicios."""
import pytest
from langchain_core.messages import HumanMessage, ToolMessage
from app.agents.decentralized.handoffs import (
    ALLOWED_HANDOFFS, HANDOFF_TOOLS, handoff_reason,
    validate_handoff, make_handoff_record,
)

AVAILABLE = {"soporte", "tecnico", "ventas", "almacen"}


@pytest.mark.parametrize("origin,destination", [
    (origin, destination) for origin, targets in ALLOWED_HANDOFFS.items() for destination in targets
])
def test_matriz_completa_valida_con_agentes_disponibles(origin, destination):
    validate_handoff(origin, destination, "Colaboración justificada", set(ALLOWED_HANDOFFS), 1)


@pytest.mark.parametrize("origin,destination,reason,available,revision", [
    ("soporte", "soporte", "Motivo", AVAILABLE, None),
    ("desconocido", "ventas", "Motivo", AVAILABLE, None),
    ("soporte", "desconocido", "Motivo", AVAILABLE, None),
    ("soporte", "almacen", "Motivo", AVAILABLE, None),
    ("soporte", "software", "Motivo", AVAILABLE, None),
    ("software", "tecnico", "Motivo", AVAILABLE, None),
    ("soporte", "ventas", " ", AVAILABLE, None),
    ("soporte", "ventas", None, AVAILABLE, None),
    ("soporte", "ventas", "Motivo", AVAILABLE, True),
    ("soporte", "ventas", "Motivo", AVAILABLE, -1),
])
def test_transferencia_invalida(origin, destination, reason, available, revision):
    with pytest.raises(ValueError):
        validate_handoff(origin, destination, reason, available, revision)


def test_repeticion_y_retorno_legitimo():
    state = {"messages": [HumanMessage(content="Consulta")], "request_revision": 1}
    first = make_handoff_record(state, "ventas", "tecnico", "Compatibilidad", AVAILABLE)
    state["handoff_records"] = [first]
    # Volver a Ventas es otra conexión válida, aunque no haya avance todavía.
    make_handoff_record(state, "tecnico", "ventas", "solo servicio", AVAILABLE)
    with pytest.raises(ValueError, match="repetida"):
        make_handoff_record(state, "ventas", "tecnico", "Otro motivo no es evidencia", AVAILABLE)
    state["messages"].append(ToolMessage(content="Nueva evidencia técnica", name="consultar_documentacion",
                                         tool_call_id="doc"))
    make_handoff_record(state, "ventas", "tecnico", "Reevaluar evidencia", AVAILABLE)
    assert "Consulta" not in str(first)


def test_ids_o_motivos_no_simulan_progreso_y_revision_si():
    state = {"messages": [ToolMessage(content="TRANSFERIR_TECNICO: Motivo", name="transferir_a_tecnico",
                                        tool_call_id="a")], "request_revision": 1}
    first = make_handoff_record(state, "ventas", "tecnico", "Motivo", AVAILABLE)
    state["handoff_records"] = [first]
    state["messages"] = [ToolMessage(content="TRANSFERIR_TECNICO: Nuevo texto", name="transferir_a_tecnico",
                                     tool_call_id="b")]
    with pytest.raises(ValueError):
        make_handoff_record(state, "ventas", "tecnico", "Nuevo texto", AVAILABLE)
    state["request_revision"] = 2
    make_handoff_record(state, "ventas", "tecnico", "Nueva solicitud", AVAILABLE)


def test_motivo_legacy_y_estructurado():
    assert handoff_reason([ToolMessage(content="TRANSFERIR_VENTAS: Precio", name="transferir_a_ventas",
                                       tool_call_id="a")]) == "Precio"
    assert handoff_reason([ToolMessage(content='{"motivo":"Cotizar"}', name="transferir_a_ventas",
                                       tool_call_id="b")]) == "Cotizar"
    assert handoff_reason([ToolMessage(content='{}', name="transferir_a_ventas", tool_call_id="c")]) is None
    assert HANDOFF_TOOLS["transferir_a_software"] == "software"


def test_repetir_resultado_identico_no_es_informacion_nueva():
    state = {"messages": [ToolMessage(content="Mismo documento", name="consultar_documentacion",
                                        tool_call_id="a")]}
    state["handoff_records"] = [make_handoff_record(state, "ventas", "tecnico", "Verificar", AVAILABLE)]
    state["messages"].append(ToolMessage(content="Mismo documento", name="consultar_documentacion",
                                         tool_call_id="b"))
    with pytest.raises(ValueError, match="repetida"):
        make_handoff_record(state, "ventas", "tecnico", "Verificar", AVAILABLE)


def test_json_formato_y_inventario_duplicado_no_simulan_progreso():
    from app.agents.decentralized.handoffs import progress_token
    state = {"messages": [ToolMessage(content='{"stock":3,"price":"180"}', name="consulta", tool_call_id="a")],
             "inventory_results": [{"stock": 3, "tool_call_id": "a"}]}
    token = progress_token(state)
    state["messages"].append(ToolMessage(content=' {"price": "180", "stock": 3}', name="consulta", tool_call_id="b"))
    state["inventory_results"].append({"stock": 3, "tool_call_id": "b"})
    assert progress_token(state) == token
    state["inventory_results"].append({"stock": 2, "tool_call_id": "c"})
    assert progress_token(state) != token


def test_consulta_vacia_no_recibe_motivo_implicito():
    from langchain_core.messages import AIMessage
    messages = [AIMessage(content="", tool_calls=[dict(name="solicitar_inventario", args={"consulta": " "}, id="a")]),
                ToolMessage(content='{"consulta":" "}', name="solicitar_inventario", tool_call_id="a")]
    assert handoff_reason(messages) is None
