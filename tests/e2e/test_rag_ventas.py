from langchain_core.messages import HumanMessage
from app.agents.decentralized.ventas import ventas_node
from app.rag.tools import consultar_base_conocimiento


def test_rag_ventas():
    state = {
        "messages": [
            HumanMessage(
                content=(
                    "Soy del área de Ventas. Consulta la base "
                    "de conocimiento para identificar los "
                    "servicios documentados que ofrecemos."
                )
            )
        ]
    }

    resultado = ventas_node(state)

    assert resultado.get("errors", []) == []

    llamadas = [
        llamada
        for mensaje in resultado["messages"]
        for llamada in getattr(mensaje, "tool_calls", [])
    ]

    nombres = [llamada["name"] for llamada in llamadas]

    print("\nHerramientas solicitadas:", nombres)

    assert "consultar_base_conocimiento" in nombres

    # Ejecutamos directamente la herramienta RAG
    llamada_rag = next(
        llamada
        for llamada in llamadas
        if llamada["name"] == "consultar_base_conocimiento"
    )

    respuesta = consultar_base_conocimiento.invoke(
        llamada_rag["args"]
    )

    print("\nInformación recuperada:")
    print(respuesta)

    assert "Fuente: ventas.md" in respuesta