from langchain_core.messages import HumanMessage, ToolMessage

from app.agents.decentralized.graph import graph


def test_rag_soporte():
    resultado = graph.invoke({
        "messages": [
            HumanMessage(
                content=(
                    "Consulta la base de conocimiento "
                    "y dime qué información se necesita "
                    "para registrar una incidencia."
                )
            )
        ]
    })

    herramientas = [
        mensaje.name
        for mensaje in resultado["messages"]
        if isinstance(mensaje, ToolMessage)
    ]

    print("\nHerramientas ejecutadas:", herramientas)

    assert "consultar_base_conocimiento" in herramientas
    assert resultado.get("errors", []) == []