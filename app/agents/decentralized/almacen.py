from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain_core.messages import (
    SystemMessage,
    HumanMessage,
    AIMessage,
    ToolMessage,
)

from app.agents.decentralized.state import AgentState
from app.agents.decentralized.policy import handoff, latest_user_message, extract_inventory_reference, contains_placeholder
from app.agents.decentralized.policy import prepare_inventory_request, evaluate_supply, build_supply_handoff
from app.agents.decentralized.tools.almacen_tools import (
    check_inventory,
)

from app.agents.decentralized.tools.warehouse_handoff_tools import transfer_to_sales, transfer_to_purchasing

# =========================================================
# CONFIGURACIÓN DEL MODELO
# =========================================================

load_dotenv()

llm = ChatGroq(
    model="openai/gpt-oss-20b",
    temperature=0,
    reasoning_effort="low",
    model_kwargs={
        "parallel_tool_calls": False,
    },
)

# =========================================================
# HERRAMIENTAS
# =========================================================

warehouse_tools = [
    check_inventory,
    transfer_to_sales,
    transfer_to_purchasing,
]

almacen_tools = warehouse_tools
almacen_llm = llm.bind_tools(warehouse_tools)


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
- Utiliza check_inventory para verificar repuestos.
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
- Con artículos identificados y faltantes confirmados, utiliza transfer_to_purchasing.
- Con stock suficiente utiliza transfer_to_sales. Una consulta completada no
  significa stock suficiente. Referencias ambiguas/no encontradas y errores
  requieren aclaración; no son stock cero confirmado ni autorizan pedidos.
- Primero verifica los repuestos con check_inventory.
- Con resultados completos, aplica la política de disponibilidad antes de transferir.
- Incluye nombre, cantidad, stock, precio y disponibilidad.
- Si algún repuesto no está disponible, indícalo.
- Si una consulta falló, indica que no fue verificada.
- Nunca inventes resultados ni precios.
"""


# =========================================================
# CONSTRUCCIÓN DEL CONTEXTO
# =========================================================

def build_warehouse_context(state: AgentState):
    """
    Construye el historial relevante para Almacén.

    Conserva:
    - Mensajes del usuario.
    - Solicitudes de transferencia desde Técnico.
    - Diagnósticos técnicos previos.
    - Llamadas y resultados de herramientas de Almacén.

    Evita incluir herramientas internas innecesarias.
    """

    context = []
    inventory_calls = set()

    tool_names = {
        "consultar_inventario",
        "check_inventory",
        "transferir_a_ventas",
        "transfer_to_sales",
    }

    # Identificar llamadas realizadas por Almacén.
    for message in state["messages"]:
        if isinstance(message, AIMessage):
            for tool_call in message.tool_calls:
                if tool_call["name"] in tool_names:
                    inventory_calls.add(tool_call["id"])

    # Construir el contexto.
    for message in state["messages"]:

        if isinstance(message, HumanMessage):
            context.append(message)

        elif isinstance(message, AIMessage):
            if message.tool_calls and all(
                tool_call["id"] in inventory_calls
                for tool_call in message.tool_calls
            ):
                context.append(message)

        elif isinstance(message, ToolMessage):

            # Resultados de las herramientas de Almacén.
            if message.tool_call_id in inventory_calls:
                context.append(message)

            # Diagnósticos realizados por Técnico.
            elif (
                message.name in {"diagnosticar_problema", "diagnose_issue"}
                and message.status != "error"
            ):
                context.append(
                    HumanMessage(
                        content=(
                            "Diagnóstico técnico previo:\n"
                            f"{message.content}"
                        )
                    )
                )

            # Solicitud de Técnico hacia Almacén.
            elif (
                message.name in {"transferir_a_almacen", "transfer_to_warehouse"}
                and message.status != "error"
            ):
                context.append(
                    HumanMessage(
                        content=(
                            "Solicitud recibida del agente Técnico:\n"
                            f"{message.content}"
                        )
                    )
                )

    return context


# =========================================================
# NODO DEL AGENTE ALMACÉN
# =========================================================

def warehouse_node(state: AgentState):
    """
    Procesa solicitudes de inventario.

    Utiliza el modelo vinculado a las herramientas
    y controla los errores de ejecución.
    """

    # Repuestos del estado: la herramienta consulta exactamente la solicitud,
    # sin dejar que el modelo sustituya un nombre genérico por otro producto.
    if state.get("inventory_query"):
        user = latest_user_message(state)
        name = extract_inventory_reference(user)
        intake = state.get("intake") or {}
        requested = extract_inventory_reference(str(intake.get("product_description", "")))
        if not name and state.get("request_type") == "SALE":
            name = requested
        quantity = 1
        if state.get("request_type") == "SALE" and name and name == requested:
            quantity = intake.get("quantity", 1)
            if type(quantity) is not int or quantity <= 0:
                return {"current_agent": "almacen", "messages": [AIMessage(content="Indica una cantidad entera positiva antes de consultar inventario.")]}
        if not name:
            return {"current_agent": "almacen", "messages": [AIMessage(content=(
                "Por ahora puedo consultar un repuesto identificado, pero no listar todas las opciones del catálogo. "
                "Indica su referencia real (capacidad e interfaz, si es un SSD), sin corchetes. "
                "No seleccionaré una variante por ti."
            ))]}
        prepared = prepare_inventory_request(state, [{"name": name, "quantity": quantity}])
        if not prepared["inventory_pending"]:
            return build_supply_handoff({**state, **prepared, "inventory_query": None})
        else:
            update = handoff("almacen", "check_inventory", part_name=name, quantity=quantity)
        update.update(prepared, inventory_query=None, quote_scope="repuestos")
        return update
    required = state.get("required_parts", [])
    if required:
        if any("inventario" in e.lower() for e in state.get("errors", [])):
            return {"current_agent": "almacen", "messages": [AIMessage(content="No se pudo verificar el inventario. No puedo confirmar una cotización.")]}
        prepared = prepare_inventory_request(state, required)
        results = prepared["inventory_results"]
        for part in required:
            if not any(r.get("requested_name") == part["name"] and r.get("quantity") == part["quantity"] for r in results):
                update = handoff("almacen", "check_inventory", part_name=part["name"], quantity=part["quantity"])
                update.update(prepared)
                return update
        return build_supply_handoff({**state, **prepared})

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        *build_warehouse_context(state),
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

construir_contexto_almacen = build_warehouse_context


almacen_node = warehouse_node
