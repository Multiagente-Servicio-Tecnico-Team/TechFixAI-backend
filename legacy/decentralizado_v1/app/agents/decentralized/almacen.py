from langchain_core.messages import (
    SystemMessage,
    HumanMessage,
    AIMessage,
    ToolMessage,
)

from app.agents.decentralized.state import AgentState
from app.config import create_chat_model
from app.agents.decentralized.policy import handoff, ultimo_usuario, nombre_inventario, es_marcador
from app.agents.decentralized.tools.almacen_tools import (
    consultar_inventario,
    transferir_a_ventas,
)

# =========================================================
# CONFIGURACIÓN DEL MODELO
# =========================================================

llm = create_chat_model()

# =========================================================
# HERRAMIENTAS
# =========================================================

almacen_tools = [
    consultar_inventario,
    transferir_a_ventas,
]

almacen_llm = llm.bind_tools(almacen_tools)


# =========================================================
# PROMPT DEL AGENTE
# =========================================================

SYSTEM_PROMPT = """
Eres el agente de Almacén y Logística de un sistema
multiagente de servicio técnico, ventas y soporte.

RESPONSABILIDADES:
- Consultar repuestos solicitados por el agente Técnico.
- Verificar disponibilidad y cantidad en inventario.
- Obtener precios unitarios reales de PostgreSQL.
- Informar si un repuesto no está disponible.

REGLAS:
- Utiliza consultar_inventario para verificar repuestos.
- Nunca inventes precios, existencias o disponibilidad.
- No consideres disponible un repuesto si la herramienta
  indica available=False.
- Si ya existe una consulta de inventario para el mismo
  repuesto y cantidad, utiliza su resultado.
- No repitas consultas innecesariamente.
- No generes cotizaciones.
- No realices diagnósticos técnicos.
- Si faltan datos para identificar un repuesto,
  no inventes nombres ni cantidades.
- Si ocurre un error de inventario, informa que no se
  pudo verificar la disponibilidad.

TRANSFERENCIA A VENTAS:
- Primero verifica los repuestos con consultar_inventario.
- Cuando tengas los resultados, utiliza transferir_a_ventas.
- Incluye nombre, cantidad, stock, precio y disponibilidad.
- Si algún repuesto no está disponible, indícalo.
- Si una consulta falló, indica que no fue verificada.
- Nunca inventes resultados ni precios.
"""


# =========================================================
# CONSTRUCCIÓN DEL CONTEXTO
# =========================================================

def construir_contexto_almacen(state: AgentState):
    """
    Construye el historial relevante para Almacén.

    Conserva:
    - Mensajes del usuario.
    - Solicitudes de transferencia desde Técnico.
    - Diagnósticos técnicos previos.
    - Llamadas y resultados de herramientas de Almacén.

    Evita incluir herramientas internas innecesarias.
    """

    contexto = []
    llamadas_almacen = set()

    nombres_tools = {
        "consultar_inventario",
        "transferir_a_ventas",
    }

    # Identificar llamadas realizadas por Almacén.
    for mensaje in state["messages"]:
        if isinstance(mensaje, AIMessage):
            for llamada in mensaje.tool_calls:
                if llamada["name"] in nombres_tools:
                    llamadas_almacen.add(llamada["id"])

    # Construir el contexto.
    for mensaje in state["messages"]:

        if isinstance(mensaje, HumanMessage):
            contexto.append(mensaje)

        elif isinstance(mensaje, AIMessage):
            if mensaje.tool_calls and all(
                llamada["id"] in llamadas_almacen
                for llamada in mensaje.tool_calls
            ):
                contexto.append(mensaje)

        elif isinstance(mensaje, ToolMessage):

            # Resultados de las herramientas de Almacén.
            if mensaje.tool_call_id in llamadas_almacen:
                contexto.append(mensaje)

            # Diagnósticos realizados por Técnico.
            elif (
                mensaje.name == "diagnosticar_problema"
                and mensaje.status != "error"
            ):
                contexto.append(
                    HumanMessage(
                        content=(
                            "Diagnóstico técnico previo:\n"
                            f"{mensaje.content}"
                        )
                    )
                )

            # Solicitud de Técnico hacia Almacén.
            elif (
                mensaje.name == "transferir_a_almacen"
                and mensaje.status != "error"
            ):
                contexto.append(
                    HumanMessage(
                        content=(
                            "Solicitud recibida del agente Técnico:\n"
                            f"{mensaje.content}"
                        )
                    )
                )

    return contexto


# =========================================================
# NODO DEL AGENTE ALMACÉN
# =========================================================

def almacen_node(state: AgentState):
    """
    Procesa solicitudes de inventario.

    Utiliza el modelo vinculado a las herramientas
    y controla los errores de ejecución.
    """

    # Repuestos del estado: la herramienta consulta exactamente la solicitud,
    # sin dejar que el modelo sustituya un nombre genérico por otro producto.
    if state.get("inventory_query"):
        user = ultimo_usuario(state)
        name = nombre_inventario(user)
        if not name:
            return {"current_agent": "almacen", "messages": [AIMessage(content=(
                "Por ahora puedo consultar un repuesto identificado, pero no listar todas las opciones del catálogo. "
                "Indica su referencia real (capacidad e interfaz, si es un SSD), sin corchetes. "
                "No seleccionaré una variante por ti."
            ))]}
        update = handoff("almacen", "consultar_inventario", nombre_repuesto=name, cantidad=1)
        update.update(required_parts=[{"name": name, "quantity": 1}], inventory_pending=True,
                      inventory_query=None, inventory_results=[], quote_scope="repuestos")
        return update
    required = state.get("required_parts", [])
    if required:
        if any("inventario" in e.lower() for e in state.get("errors", [])):
            return {"current_agent": "almacen", "messages": [AIMessage(content="No se pudo verificar el inventario. No puedo confirmar una cotización.")]}
        results = state.get("inventory_results", [])
        for part in required:
            if not any(r.get("requested_name") == part["name"] and r.get("quantity") == part["quantity"] for r in results):
                return handoff("almacen", "consultar_inventario", nombre_repuesto=part["name"], cantidad=part["quantity"])
        return handoff("almacen", "transferir_a_ventas", motivo="Inventario verificado")

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        *construir_contexto_almacen(state),
    ]

    try:
        response = almacen_llm.invoke(messages)

        return {
            "messages": [response],
            "current_agent": "almacen",
        }

    except Exception as e:
        error = (
            f"Error en el agente Almacén: "
            f"{type(e).__name__}"
        )

        return {
            "messages": [
                AIMessage(
                    content=(
                        "No fue posible consultar el inventario "
                        "en este momento."
                    )
                )
            ],
            "current_agent": "almacen",
            "errors": state.get("errors", []) + [error],
        }
import importlib as _importlib
import sys as _sys

_sys.modules[__name__] = _importlib.import_module(".warehouse", __package__)
