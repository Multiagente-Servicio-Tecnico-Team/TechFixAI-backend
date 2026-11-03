from langchain_core.messages import HumanMessage, ToolMessage
from app.agents.decentralized.graph import graph


def test_rag_tecnico():
    resultado = graph.invoke({
        "messages": [
            HumanMessage(
                content=(
                    "Necesito que me atienda el agente Técnico. "
                    "Mi computadora no enciende. "
                    "Quiero conocer los procedimientos documentados "
                    "en la base de conocimiento para revisar "
                    "la fuente de poder, el cable de alimentación "
                    "y la batería. Consulta esa documentación."
    )
)
        ]
    })

    agente_actual = "soporte"
    herramientas_por_agente = {
        "soporte": [],
        "tecnico": [],
        "ventas": [],
    }

    for mensaje in resultado["messages"]:
        if not isinstance(mensaje, ToolMessage):
            continue

        herramientas_por_agente[agente_actual].append(mensaje.name)

        if mensaje.name == "transferir_a_tecnico":
            agente_actual = "tecnico"
        elif mensaje.name == "transferir_a_ventas":
            agente_actual = "ventas"

    print("\nHerramientas por agente:", herramientas_por_agente)
    print("Historial:", resultado.get("handoff_history", []))

    print("\nMensajes del flujo:")

    for mensaje in resultado["messages"]:
        print(
            type(mensaje).__name__,
            getattr(mensaje, "name", ""),
            str(mensaje.content)[:500]
        )

    assert "transferir_a_tecnico" in herramientas_por_agente["soporte"]
    assert "consultar_base_conocimiento" in herramientas_por_agente["tecnico"]
    assert resultado.get("errors", []) == []