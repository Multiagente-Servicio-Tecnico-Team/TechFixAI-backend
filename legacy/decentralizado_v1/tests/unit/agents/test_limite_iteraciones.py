
from langchain_core.messages import ToolMessage

from app.agents.decentralized.graph import (
    registrar_handoff,
    MAX_TOOL_ITERATIONS,
)


def test_limite_iteraciones_ventas():
    state = {
        "messages": [
            ToolMessage(
                content="Información recuperada",
                name="consultar_base_conocimiento",
                tool_call_id="test-rag",
            )
        ],
        "tool_iterations": {
            "ventas": MAX_TOOL_ITERATIONS - 1
        },
        "errors": [],
    }

    resultado = registrar_handoff(state, "ventas")

    assert resultado["next_agent"] == "finalizar"
    assert (
        resultado["tool_iterations"]["ventas"]
        == MAX_TOOL_ITERATIONS
    )
    assert any(
        "Límite de herramientas" in error
        for error in resultado["errors"]
    )


def test_iteraciones_dentro_del_limite():
    state = {
        "messages": [
            ToolMessage(
                content="Información recuperada",
                name="consultar_base_conocimiento",
                tool_call_id="test-rag",
            )
        ],
        "tool_iterations": {
            "ventas": 2
        },
        "errors": [],
    }

    resultado = registrar_handoff(state, "ventas")

    assert resultado["next_agent"] == "ventas"
    assert resultado["tool_iterations"]["ventas"] == 3
    assert resultado.get("errors", []) == []
