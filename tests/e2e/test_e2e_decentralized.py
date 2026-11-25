import pytest

from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    ToolMessage,
)

from test_software_e2e import network, pairs


@pytest.mark.e2e
def test_flujo_soporte_tecnico_ventas(network):
    """
    Comprueba el flujo real entre agentes.
    Grafo, agentes, herramientas y auditoría reales; modelo y RAG aislados.
    Cotizar una revisión de diagnóstico no implica ejecutar un diagnóstico.
    """

    estado = {
        "messages": [
            HumanMessage(
                content=(
                    "Mi computadora no enciende. "
                    "Necesito un diagnóstico y también "
                    "una cotización para repararla."
                )
            )
        ],
        "handoff_count": 0,
        "handoff_history": [],
        "errors": [],
    }

    graph_module, _ = network
    resultado = graph_module.build_graph().invoke(
        estado,
        config={"recursion_limit": 30},
    )

    print("\n=== RESPUESTAS DE LOS AGENTES ===")

    for mensaje in resultado["messages"]:
        if isinstance(mensaje, AIMessage):
            if mensaje.content and not mensaje.tool_calls:
                print(mensaje.content)

    print("\n=== HERRAMIENTAS EJECUTADAS ===")

    herramientas = [
        mensaje.name
        for mensaje in resultado["messages"]
        if isinstance(mensaje, ToolMessage)
    ]

    print(herramientas)

    print("\n=== TRANSFERENCIAS ===")
    print(resultado.get("handoff_history", []))

    print("\n=== ERRORES ===")
    print(resultado.get("errors", []))

    # Comprobaciones básicas
    assert resultado.get("errors", []) == []

    assert herramientas == ["transfer_to_hardware", "transfer_to_sales"]
    assert resultado["handoff_history"] == [
        {"origin": "soporte", "destination": "tecnico"},
        {"origin": "tecnico", "destination": "ventas"},
    ]
    assert resultado["current_agent"] == "ventas"
    assert resultado["quote_scope"] == "solo_servicio"
    assert not resultado.get("required_parts")
    assert not resultado.get("technical_assessment")
    assert not resultado.get("ticket_id") and not resultado.get("quote_id")
    assert resultado["quote"]["total"] is None
    transfers = [call for message in resultado["messages"] if isinstance(message, AIMessage)
                 for call in message.tool_calls if call["name"] == "transfer_to_sales"]
    assert len(transfers) == 1
    assert transfers[0]["args"]["scope"] == "solo_servicio"
    pairs(resultado)

    respuesta_final = resultado["messages"][-1]

    assert isinstance(respuesta_final, AIMessage)
    assert respuesta_final.content.strip()
