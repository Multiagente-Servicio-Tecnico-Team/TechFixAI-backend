import pytest

from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    ToolMessage,
)

from app.agents.decentralized.graph import graph


@pytest.mark.e2e
def test_flujo_soporte_tecnico_ventas():
    """
    Comprueba el flujo real entre agentes.
    Requiere Groq y conexión a Internet.
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

    resultado = graph.invoke(
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

    assert "diagnosticar_problema" in herramientas

    respuesta_final = resultado["messages"][-1]

    assert isinstance(respuesta_final, AIMessage)
    assert respuesta_final.content.strip()