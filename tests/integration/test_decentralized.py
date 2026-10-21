import json
import pytest

from langchain_core.messages import (
    AIMessage,
    ToolMessage,
)

from app.agents.decentralized.graph import (
    detectar_handoff,
    registrar_handoff,
    route_next_agent,
    MAX_HANDOFFS,
)

# TEST 1: DETECCIÃ“N DE TRANSFERENCIAS
def test_detectar_handoff_tecnico():
    mensajes = [
        ToolMessage(
            content="TRANSFERIR_TECNICO: Problema",
            name="transferir_a_tecnico",
            tool_call_id="test-1",
        )
    ]

    assert detectar_handoff(mensajes) == "tecnico"

# TEST 2: TRANSFERENCIA A VENTAS
def test_detectar_handoff_ventas():
    mensajes = [
        ToolMessage(
            content="TRANSFERIR_VENTAS: Precio",
            name="transferir_a_ventas",
            tool_call_id="test-2",
        )
    ]

    assert detectar_handoff(mensajes) == "ventas"

# TEST 3: REGISTRO DEL HISTORIAL
def test_registrar_handoff():
    estado = {
        "messages": [
            ToolMessage(
                content="TRANSFERIR_VENTAS: CotizaciÃ³n",
                name="transferir_a_ventas",
                tool_call_id="test-3",
            )
        ],
        "handoff_count": 0,
        "handoff_history": [],
        "errors": [],
    }

    resultado = registrar_handoff(estado, "soporte")

    assert resultado["next_agent"] == "ventas"
    assert resultado["handoff_count"] == 1
    assert resultado["handoff_history"] == [
        {"origen": "soporte", "destino": "ventas"}
    ]


# TEST 4: LÃMITE DE TRANSFERENCIAS

def test_limite_handoffs():
    estado = {
        "messages": [
            ToolMessage(
                content="TRANSFERIR_TECNICO: Problema",
                name="transferir_a_tecnico",
                tool_call_id="test-4",
            )
        ],
        "handoff_count": MAX_HANDOFFS,
        "handoff_history": [],
        "errors": [],
    }

    resultado = registrar_handoff(estado, "soporte")

    assert resultado["next_agent"] == "finalizar"
    assert resultado["errors"]
    assert any(
        isinstance(mensaje, AIMessage)
        for mensaje in resultado["messages"]
    )


# TEST 5: ENRUTAMIENTO

def test_route_next_agent():
    estado = {
        "messages": [],
        "next_agent": "ventas",
    }

    assert route_next_agent(estado) == "ventas"


# TEST 6: SIN TRANSFERENCIA

def test_sin_handoff():
    mensajes = [
        ToolMessage(
            content="Servicio: mantenimiento",
            name="generar_cotizacion",
            tool_call_id="test-6",
        )
    ]

    assert detectar_handoff(mensajes) is None

def test_error_groq_ventas(monkeypatch):
    from langchain_core.messages import HumanMessage
    from app.agents.decentralized import ventas

    # Simulamos un modelo que falla
    class ModeloFallido:
        def invoke(self, *args, **kwargs):
            raise RuntimeError("API no disponible")

    # Reemplazamos temporalmente el modelo
    monkeypatch.setattr(
        ventas,
        "ventas_llm",
        ModeloFallido()
    )

    estado = {
        "messages": [
            HumanMessage(
                content="Â¿CuÃ¡nto cuesta el mantenimiento?"
            )
        ],
        "errors": [],
    }

    resultado = ventas.ventas_node(estado)

    assert resultado["current_agent"] == "ventas"
    assert resultado["errors"]
    assert "RuntimeError" in resultado["errors"][0]
    assert "No fue posible" in resultado["messages"][0].content

def test_error_groq_soporte(monkeypatch):
    from langchain_core.messages import HumanMessage
    from app.agents.decentralized import soporte

    # Simulamos un modelo que falla
    class ModeloFallido:
        def invoke(self, *args, **kwargs):
            raise RuntimeError("API no disponible")

    monkeypatch.setattr(
        soporte,
        "soporte_llm",
        ModeloFallido()
    )

    estado = {
        "messages": [
            HumanMessage(
                content="Necesito ayuda con mi computadora"
            )
        ],
        "errors": [],
    }

    resultado = soporte.soporte_node(estado)

    assert resultado["current_agent"] == "soporte"
    assert resultado["errors"]
    assert "RuntimeError" in resultado["errors"][0]
    assert "No fue posible" in resultado["messages"][0].content


def test_error_groq_tecnico(monkeypatch):
    from langchain_core.messages import HumanMessage
    from app.agents.decentralized import tecnico

    # Simulamos un modelo que falla
    class ModeloFallido:
        def invoke(self, *args, **kwargs):
            raise RuntimeError("API no disponible")

    monkeypatch.setattr(
        tecnico,
        "tecnico_llm",
        ModeloFallido()
    )

    estado = {
        "messages": [
            HumanMessage(
                content="Mi computadora no enciende"
            )
        ],
        "errors": [],
    }

    resultado = tecnico.tecnico_node(estado)

    assert resultado["current_agent"] == "tecnico"
    assert resultado["errors"]
    assert "RuntimeError" in resultado["errors"][0]
    assert "No fue posible" in resultado["messages"][0].content


def test_error_herramienta():
    from langchain_core.tools import tool
    from langchain_core.messages import AIMessage
    from langgraph.prebuilt import ToolNode
    from langgraph.graph import StateGraph, START, END
    from app.agents.decentralized.state import AgentState

    # Herramienta que falla intencionalmente
    @tool
    def herramienta_fallida(valor: str) -> str:
        """Herramienta que simula un error."""
        raise RuntimeError("Fallo simulado")

    # Creamos el nodo de herramientas
    nodo = ToolNode(
        [herramienta_fallida],
        handle_tool_errors=True
    )

    # Construimos un grafo mÃnimo
    builder = StateGraph(AgentState)

    builder.add_node("herramientas", nodo)

    builder.add_edge(START, "herramientas")
    builder.add_edge("herramientas", END)

    grafo = builder.compile()

    # Simulamos una llamada a la herramienta
    estado = {
        "messages": [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "herramienta_fallida",
                        "args": {"valor": "prueba"},
                        "id": "call-test"
                    }
                ]
            )
        ]
    }

    # Ejecutamos el grafo
    resultado = grafo.invoke(estado)

    # Obtenemos el mensaje generado
    mensaje = resultado["messages"][-1]

    # Verificamos que se capturÃ³ el error
    assert mensaje.status == "error"
    assert mensaje.tool_call_id == "call-test"
    assert "RuntimeError" in mensaje.content

# PRUEBAS DEL CONTEXTO DE VENTAS

from langchain_core.messages import HumanMessage

from app.agents.decentralized.ventas import (
    construir_contexto_ventas,
)


# TEST 11: CONSERVAR MENSAJES DEL USUARIO
def test_ventas_contexto_usuario():
    estado = {
        "messages": [
            HumanMessage(content="Quiero una cotizaciÃ³n")
        ]
    }

    contexto = construir_contexto_ventas(estado)

    assert len(contexto) == 1
    assert isinstance(contexto[0], HumanMessage)


# TEST 12: CONSERVAR HERRAMIENTAS DE VENTAS
def test_ventas_contexto_cotizacion():
    llamada = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "generar_cotizacion",
                "args": {"servicio": "reparacion"},
                "id": "call-ventas",
            }
        ],
    )

    resultado = ToolMessage(
        content="Precio estimado: S/ 120",
        name="generar_cotizacion",
        tool_call_id="call-ventas",
    )

    estado = {
        "messages": [llamada, resultado]
    }

    contexto = construir_contexto_ventas(estado)

    assert len(contexto) == 2
    assert contexto[0] == llamada
    assert contexto[1] == resultado


# TEST 13: EXCLUIR TRANSFERENCIAS DE SOPORTE
def test_ventas_excluir_handoff_soporte():
    llamada = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "transferir_a_ventas",
                "args": {"motivo": "CotizaciÃ³n"},
                "id": "call-soporte",
            }
        ],
    )

    resultado = ToolMessage(
        content="TRANSFERIR_VENTAS: CotizaciÃ³n",
        name="transferir_a_ventas",
        tool_call_id="call-soporte",
    )

    estado = {
        "messages": [llamada, resultado]
    }

    contexto = construir_contexto_ventas(estado)

    assert contexto == []


# TEST 14: CONSERVAR DIAGNÃ“STICO TÃ‰CNICO
def test_ventas_contexto_diagnostico():
    diagnostico = ToolMessage(
        content="Posible falla en la fuente",
        name="diagnosticar_problema",
        tool_call_id="call-tecnico",
    )

    estado = {
        "messages": [diagnostico]
    }

    contexto = construir_contexto_ventas(estado)

    assert len(contexto) == 1
    assert isinstance(contexto[0], HumanMessage)
    assert "Diagnóstico técnico previo" in contexto[0].content
    assert "fuente" in contexto[0].content


# TEST 15: EXCLUIR MENSAJES INTERNOS
def test_ventas_excluir_mensajes_internos():
    respuesta = AIMessage(content="¿Qué capacidad necesitas?")
    estado = {
        "messages": [
            respuesta,
            AIMessage(content="", tool_calls=[{
                "name": "herramienta_ajena", "args": {}, "id": "call-ajena",
            }]),
            ToolMessage(
                content="Resultado ajeno",
                name="herramienta_ajena",
                tool_call_id="call-ajena",
            ),
        ]
    }

    contexto = construir_contexto_ventas(estado)

    assert contexto == [respuesta]


# PRUEBAS ADICIONALES DEL GRAFO
from app.agents.decentralized.graph import (
    auditar_soporte,
    auditar_tecnico,
    auditar_ventas,
)


# TEST 16: SIN RESULTADOS DE HERRAMIENTAS
def test_detectar_handoff_sin_tools():
    mensajes = [
        AIMessage(content="Respuesta normal")
    ]

    assert detectar_handoff(mensajes) is None


# TEST 17: TRANSFERENCIA CON ERROR
def test_detectar_handoff_error():
    mensajes = [
        ToolMessage(
            content="Error de herramienta",
            name="transferir_a_tecnico",
            tool_call_id="error-1",
            status="error",
        )
    ]

    assert detectar_handoff(mensajes) is None


# TEST 18: HERRAMIENTA DESCONOCIDA
def test_detectar_handoff_desconocido():
    mensajes = [
        ToolMessage(
            content="Resultado",
            name="herramienta_desconocida",
            tool_call_id="unknown-1",
        )
    ]

    assert detectar_handoff(mensajes) is None


# TEST 19: TRANSFERENCIA AL MISMO AGENTE
def test_handoff_mismo_agente():
    estado = {
        "messages": [
            ToolMessage(
                content="Transferencia",
                name="transferir_a_tecnico",
                tool_call_id="same-1",
            )
        ],
        "handoff_count": 0,
        "handoff_history": [],
        "errors": [],
    }

    resultado = registrar_handoff(estado, "tecnico")

    assert resultado["next_agent"] == "finalizar"
    assert "Transferencia al mismo agente" in resultado["errors"]


# TEST 20: CONTINUAR SIN HANDOFF
def test_registrar_sin_handoff():
    estado = {
        "messages": [
            AIMessage(content="Respuesta normal")
        ]
    }

    resultado = registrar_handoff(estado, "soporte")

    assert resultado["next_agent"] == "soporte"


# TEST 21: AUDITORÃA DE SOPORTE
def test_auditar_soporte():
    estado = {"messages": []}

    resultado = auditar_soporte(estado)

    assert resultado["next_agent"] == "soporte"


# TEST 22: AUDITORÃA DE TÃ‰CNICO
def test_auditar_tecnico():
    estado = {"messages": []}

    resultado = auditar_tecnico(estado)

    assert resultado["next_agent"] == "tecnico"


# TEST 23: AUDITORÃA DE VENTAS
def test_auditar_ventas():
    estado = {"messages": []}

    resultado = auditar_ventas(estado)

    assert resultado["next_agent"] == "ventas"


# TEST 24: DESTINO NO DEFINIDO
def test_route_next_agent_default():
    estado = {"messages": []}

    assert route_next_agent(estado) == "finalizar"



# TEST 25: HANDOFF ESTRUCTURADO A ALMACEN
def test_handoff_almacen_registra_repuesto():
    estado = {
        "messages": [HumanMessage(content="Necesito Memoria RAM 16GB DDR4 3200MHz"), ToolMessage(
            content=json.dumps({
                "accion": "TRANSFERIR_ALMACEN",
                "motivo": "Reemplazo confirmado",
                "nombre_repuesto": "Memoria RAM 16GB DDR4 3200MHz",
                "cantidad": 1,
            }),
            name="transferir_a_almacen",
            tool_call_id="parte-25",
        )],
        "handoff_count": 0,
        "handoff_history": [],
        "errors": [],
    }
    resultado = registrar_handoff(estado, "tecnico")
    assert resultado["next_agent"] == "almacen"
    assert resultado["required_parts"] == [
        {"name": "Memoria RAM 16GB DDR4 3200MHz", "quantity": 1}
    ]
    assert resultado["inventory_pending"] is True
    assert resultado["handoff_count"] == 1
    assert resultado["handoff_history"] == [
        {"origen": "tecnico", "destino": "almacen"}
    ]
    assert not resultado.get("errors")


# TEST 26: NO TRANSFERIR SIN NOMBRE DE REPUESTO
def test_handoff_almacen_rechaza_nombre_vacio():
    estado = {
        "messages": [ToolMessage(
            content=json.dumps({"error": "Nombre obligatorio"}),
            name="transferir_a_almacen",
            tool_call_id="parte-26",
        )],
        "handoff_count": 0,
        "handoff_history": [],
        "errors": [],
    }
    resultado = registrar_handoff(estado, "tecnico")
    assert resultado["next_agent"] == "finalizar"
    assert resultado.get("required_parts", []) == []
    assert resultado.get("handoff_count", 0) == 0
    assert resultado.get("handoff_history", []) == []
    assert resultado.get("errors")


# TEST 27: RECHAZAR CANTIDAD INVALIDA
@pytest.mark.parametrize("cantidad", [0, -1, True, "2", None])
def test_handoff_almacen_rechaza_cantidad_invalida(cantidad):
    estado = {
        "messages": [ToolMessage(
            content=json.dumps({
                "accion": "TRANSFERIR_ALMACEN",
                "nombre_repuesto": "RAM",
                "cantidad": cantidad,
            }),
            name="transferir_a_almacen",
            tool_call_id="parte-27",
        )],
        "handoff_count": 0,
        "handoff_history": [],
        "errors": [],
    }
    resultado = registrar_handoff(estado, "tecnico")
    assert resultado["next_agent"] == "finalizar"
    assert resultado.get("required_parts", []) == []
    assert resultado.get("handoff_count", 0) == 0
    assert resultado.get("errors")


# TEST 28: RECHAZAR FALLO EXPLICITO DE HERRAMIENTA
def test_handoff_almacen_rechaza_error_herramienta():
    estado = {
        "messages": [ToolMessage(
            content="Error simulado",
            name="transferir_a_almacen",
            tool_call_id="parte-28",
            status="error",
        )],
        "handoff_count": 0,
        "handoff_history": [],
        "errors": [],
    }
    resultado = registrar_handoff(estado, "tecnico")
    assert resultado.get("next_agent") != "almacen"
    assert resultado.get("required_parts", []) == []
    assert resultado.get("handoff_count", 0) == 0
