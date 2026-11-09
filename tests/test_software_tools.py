"""Pruebas locales de transferencias; no cargan grafo, modelo, RAG ni BD."""
import json

import pytest
from langchain_core.messages import AIMessage, ToolMessage
from pydantic import ValidationError

from app.agents.decentralized.handoffs import (
    HANDOFF_TOOLS, handoff_reason, make_handoff_record, selected_handoff,
)
from app.agents.decentralized.tools import software_tools


CASES = [
    (software_tools.transferir_a_soporte, "soporte", {}),
    (software_tools.transferir_a_tecnico, "tecnico", {}),
    (software_tools.transferir_a_ventas, "ventas", {"alcance": "solo_servicio"}),
]


@pytest.mark.parametrize("transfer,destination,extra", CASES)
def test_formato_nombre_y_contrato(transfer, destination, extra):
    assert transfer.name == f"transferir_a_{destination}"
    assert HANDOFF_TOOLS[transfer.name] == destination
    result = transfer.invoke({"motivo": "  Evaluación pendiente  ", **extra})
    if destination == "ventas":
        assert result == {"accion": "SOLICITAR_COTIZACION", "motivo": "Evaluación pendiente",
                          "alcance": "solo_servicio", "nombre_repuesto": "", "cantidad": 1}
        content = json.dumps(result)
    else:
        assert result == f"TRANSFERIR_{destination.upper()}: Evaluación pendiente"
        content = result
    message = ToolMessage(content=content, name=transfer.name, tool_call_id="handoff")
    assert selected_handoff([message]) is message
    assert handoff_reason([message]) == "Evaluación pendiente"
    record = make_handoff_record({"messages": [message], "request_revision": 1},
                                 "software", destination, handoff_reason([message]),
                                 {"software", "soporte", "tecnico", "ventas", "almacen"})
    assert record["destination"] == destination
    # El grafo actual aún no dispone del agente de origen Software.
    with pytest.raises(ValueError, match="no disponible"):
        make_handoff_record({"messages": [message]}, "software", destination,
                            handoff_reason([message]), {"soporte", "tecnico", "ventas", "almacen"})


@pytest.mark.parametrize("transfer,destination,extra", CASES)
@pytest.mark.parametrize("motivo", ["", " ", "\n\t", None, 12, True])
def test_rechaza_motivo_invalido(transfer, destination, extra, motivo):
    with pytest.raises((ValueError, ValidationError)):
        transfer.invoke({"motivo": motivo, **extra})


@pytest.mark.parametrize("transfer,destination,extra", CASES)
def test_motivo_obligatorio_en_esquema(transfer, destination, extra):
    assert "motivo" in transfer.args_schema.model_json_schema()["required"]
    with pytest.raises(ValidationError):
        transfer.invoke(extra)


@pytest.mark.parametrize("alcance", ["repuestos", "sin_determinar", "", None])
def test_ventas_rechaza_alcance_ajeno(alcance):
    with pytest.raises(ValidationError):
        software_tools.transferir_a_ventas.invoke({"motivo": "Servicio", "alcance": alcance})


def test_ventas_exige_alcance_explicito():
    with pytest.raises(ValidationError):
        software_tools.transferir_a_ventas.invoke({"motivo": "Servicio"})


@pytest.mark.parametrize("transfer,destination,extra", CASES)
def test_llamada_estructurada_compatible(transfer, destination, extra):
    args = {"motivo": "Evidencia pendiente", **extra}
    call = {"name": transfer.name, "args": args, "id": "llamada", "type": "tool_call"}
    result = transfer.invoke(call)
    assert isinstance(result, ToolMessage)
    assert result.name == transfer.name and result.tool_call_id == "llamada"
    assert handoff_reason([AIMessage(content="", tool_calls=[call]), result]) == args["motivo"]
