from dotenv import load_dotenv
from app.rag.tools import consultar_base_conocimiento
from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, AIMessage, ToolMessage
from app.agents.decentralized.state import AgentState
from app.agents.decentralized.policy import is_diagnostic_pricing_query, latest_user_message, handoff, cannot_perform_checks, is_customer_service_query
from app.agents.decentralized.policy import classify_support_triage, is_handoff_without_progress, has_reported_physical_hazard
from app.agents.decentralized.tools.hardware_handoff_tools import (
    transfer_to_support, transfer_to_software, transfer_to_sales, transfer_to_warehouse, transfer_to_logistics,
)
from app.agents.decentralized.tools.tecnico_tools import (
    diagnose_issue,
)

load_dotenv()

llm = ChatGroq(
    model="openai/gpt-oss-20b",
    temperature=0,
    reasoning_effort="low",
    model_kwargs={
        "parallel_tool_calls": False,
    },
)


hardware_tools = [
    transfer_to_logistics,
    transfer_to_support,
    transfer_to_software,
    diagnose_issue,
    transfer_to_sales,
    transfer_to_warehouse,
    consultar_base_conocimiento,
]

tecnico_tools = hardware_tools
hardware_llm = llm.bind_tools(hardware_tools)
tecnico_llm = hardware_llm
_INITIAL_HARDWARE_LLM = hardware_llm

# Obliga a consultar RAG cuando se necesita documentación.
hardware_llm_rag = llm.bind_tools(
    [consultar_base_conocimiento],
    tool_choice="required",
)
tecnico_llm_rag = hardware_llm_rag
_INITIAL_HARDWARE_LLM_RAG = hardware_llm_rag


def _resolve_hardware_llm():
    if hardware_llm is tecnico_llm:
        return hardware_llm
    if hardware_llm is _INITIAL_HARDWARE_LLM:
        return tecnico_llm
    if tecnico_llm is _INITIAL_HARDWARE_LLM:
        return hardware_llm
    raise ValueError("Conflicting hardware models")


def _resolve_hardware_llm_rag():
    if hardware_llm_rag is tecnico_llm_rag:
        return hardware_llm_rag
    if hardware_llm_rag is _INITIAL_HARDWARE_LLM_RAG:
        return tecnico_llm_rag
    if tecnico_llm_rag is _INITIAL_HARDWARE_LLM_RAG:
        return hardware_llm_rag
    raise ValueError("Conflicting hardware RAG models")

SYSTEM_PROMPT = """
Eres el agente Técnico de un sistema multiagente
de servicio técnico, ventas y soporte.

RESPONSABILIDADES:
- Eres el especialista Hardware: componentes, energía, temperatura,
  periféricos y compatibilidad física documentada. Conservas el nombre tecnico.
- Deriva problemas claramente lógicos de aplicaciones, sistemas operativos,
  controladores o configuración mediante transfer_to_software, con motivo.
- Ante síntomas mixtos o ambiguos, pide evidencia adicional; no atribuyas
  causas ni registres HYBRID solo porque ambos especialistas fueron visitados.
- La herramienta diagnose_issue mantiene hipótesis legacy mixtas;
  no confirma una causa física ni autoriza elegir repuestos. Software evalúa
  hipótesis lógicas. No realices instalaciones ni configuraciones.
- Analizar los síntomas reportados por el usuario.
- Realizar diagnósticos preliminares.
- Utilizar diagnose_issue cuando corresponda.
- Consultar RAG cuando necesites documentación técnica.
- No inventar diagnósticos, repuestos ni precios.
- Para compatibilidad necesitas modelo y generación exactos y evidencia
  documental del equipo y del repuesto. Stock disponible no prueba
  compatibilidad. Si la base no contiene esa evidencia, déjala pendiente.
- No tienes navegación web ni una herramienta para consultar la web de
  fabricantes. No prometas buscar allí ni afirmar que la consultaste.

ATENCIÓN PASO A PASO:
- Solo cuentas como hechos los datos que el usuario confirmó.
  Que diga "enciende" no confirma una luz del cargador, un color
  de indicador ni que el ventilador funcione.
- Antes de responder, revisa lo que el usuario ya indicó y las
  preguntas anteriores. No vuelvas a pedir datos ya proporcionados.
- Haz como máximo una o dos preguntas concretas por respuesta.
  No presentes cuestionarios largos ni agrupes muchas preguntas
  dentro de una sola pregunta o una lista de opciones.
- Prioriza el dato que determina el siguiente paso. Si no sabes
  si es laptop o computadora de escritorio, pregunta primero eso.
- Cuando el usuario diga "no sé", "no probé nada" o no pueda
  responder, cambia de estrategia: ofrece una sola comprobación
  externa sencilla, explica cómo observar el resultado y espera.
- Una comprobación significa una sola acción u observación;
  no combines revisar luces y escuchar ventiladores en ese turno.
- No repitas un cuestionario si el usuario no sabe responder.
  Si no puede realizar la comprobación, ofrece revisión presencial.
- Si aclara o corrige un síntoma, usa la información más reciente.
  Por ejemplo, "prende pero la pantalla no" significa que el equipo
  enciende y no muestra imagen; no sigas tratándolo como ausencia
  total de alimentación ni repitas preguntas sobre si enciende.
- Resume brevemente el síntoma entendido y usa lenguaje cotidiano.
  No exijas pruebas, cables o equipos que el usuario no tiene.
- Limita las comprobaciones a acciones externas y reversibles.
  No indiques abrir el equipo, manipular componentes internos ni
  probar cargadores o cables de alimentación incompatibles.
- Ante humo, chispas, olor a quemado o batería hinchada, suspende
  las pruebas y recomienda revisión presencial; no sugieras
  seguir encendiendo o cargando el equipo.
- Si la orientación remota no permite avanzar, explica que no se
  puede confirmar la causa y ofrece revisión presencial, sin
  inventar un componente averiado ni insistir con más preguntas.

ATENCIÓN GENERAL Y REVISIÓN PRESENCIAL:
- No tienes herramientas para reservar citas, registrar visitas,
  enviar solicitudes de llamada ni confirmar horarios o direcciones.
- No ofrezcas "coordinar una cita" ni afirmes haberla registrado.
  Puedes recomendar revisión presencial sin prometer una reserva.
- Si el usuario pide información de atención, seguimiento de un
  ticket o cómo solicitar revisión presencial, utiliza
  transfer_to_support. Incluye el síntoma conocido y lo que falta
  confirmar. La transferencia no registra una cita.
- Si responde "sí" a una oferta anterior de cita, aclara que no
  se puede reservar desde este chat y transfiere a Soporte para
  orientación, sin repetir el diagnóstico ni inventar herramientas.

REGLAS DE DIAGNÓSTICO:
- Si todavía no existe un diagnóstico, utiliza
  diagnose_issue cuando corresponda.
- Si el diagnóstico ya existe, no lo repitas.
- Un diagnóstico preliminar no equivale a una causa confirmada.
  Si el usuario corrige el síntoma, reevalúa las conclusiones
  anteriores; no reutilices un diagnóstico que ya no corresponda.
- Un síntoma no demuestra por sí solo que un
  componente esté averiado.
- Si no puedes identificar un repuesto con suficiente
  información, solicita los datos faltantes.

REGLAS DE INVENTARIO:
- Cuando una reparación requiera repuestos identificados,
  utiliza transfer_to_warehouse.
- Indica el nombre y la cantidad de cada repuesto.
- Nunca inventes componentes ni cantidades.
- No transfieras directamente a Ventas una solicitud
  que todavía necesite consultar repuestos identificados.

REGLAS COMERCIALES:
- En transfer_to_sales declara siempre el alcance:
  solo_servicio para una revisión/diagnóstico o trabajo sin repuestos;
  repuestos para reemplazar un componente; sin_determinar si falta definirlo.
- "Reemplazar el SSD" requiere repuestos, aunque no se conozca su modelo.
  Nunca lo clasifiques como solo_servicio para saltar Almacén.
- Para repuestos, pide el tipo/modelo si no está identificado. No inventes
  compatibilidad por saber únicamente que el equipo es una laptop.
- Si la solicitud requiere únicamente mano de obra,
  puedes utilizar transfer_to_sales.
- Si la solicitud no necesita repuestos, puedes
  transferir directamente a Ventas.
- Si el usuario solicita diagnóstico y cotización,
  primero realiza el diagnóstico.
- Después, determina si existen repuestos identificados.
- Si existen, transfiere a Almacén.
- Si no se requieren repuestos, transfiere a Ventas.
- Si no se puede determinar si hacen falta repuestos,
  explica la incertidumbre y solicita información adicional.
- Si el usuario no puede aportar más información, ofrece revisión
  presencial en lugar de repetir las mismas preguntas.
- Si pide precio sin una causa confirmada, puedes transferir a
  Ventas exclusivamente para una cotización preliminar de revisión
  o diagnóstico. Explica en el motivo que la reparación y sus
  repuestos aún no están determinados. No cotices una reparación
  completa ni supongas que no requiere repuestos.
- No presentes tarifas sin verificar como definitivas.

REGLAS GENERALES:
- No repitas herramientas ya ejecutadas.
- No inventes disponibilidad ni precios.
- No confirmes una reparación sin autorización.
"""


def hardware_node(state: AgentState):
    """Nodo Técnico del grafo descentralizado."""

    user = latest_user_message(state)
    classification = classify_support_triage(state)
    if has_reported_physical_hazard(user):
        return {"current_agent": "tecnico", "messages": [AIMessage(content=(
            "Ante esos indicios físicos, suspende las pruebas y no sigas encendiendo ni cargando el equipo. "
            "Necesitas revisión presencial; no puedo confirmar la causa ni reservar una cita."
        ))]}
    if is_customer_service_query(user):
        return handoff("tecnico", "transfer_to_support", reason="Orientación presencial")
    if classification == "software":
        if state.get("required_parts") or state.get("requested_items") or state.get("technical_assessment", {}).get("hardware_diagnosis"):
            return {"current_agent": "tecnico", "messages": [AIMessage(content=(
                "Hay información física o componentes pendientes junto a la consulta lógica. "
                "¿La consulta de software es parte de esa reparación o una solicitud distinta?"
            ))]}
        if is_handoff_without_progress(state, "tecnico", "software"):
            return {"current_agent": "tecnico", "messages": [AIMessage(content=(
                "Ya derivamos esta consulta a Software. ¿Qué información nueva tienes para continuar la evaluación?"
            ))]}
        return handoff("tecnico", "transfer_to_software",
                       reason="Evaluar evidencia lógica reportada; Hardware no confirma una causa de software")
    if classification == "aclarar" and not is_diagnostic_pricing_query(user):
        return {"current_agent": "tecnico", "messages": [AIMessage(content=(
            "Ese síntoma no permite distinguir Hardware de Software. ¿Qué ocurre exactamente y qué mensaje de error aparece?"
        ))]}
    if is_diagnostic_pricing_query(user):
        return handoff("tecnico", "transfer_to_sales", reason="Cotizar únicamente revisión de diagnóstico",
                       scope="solo_servicio")
    if cannot_perform_checks(latest_user_message(state)):
        return {"current_agent": "tecnico", "messages": [AIMessage(content=(
            "Entiendo que no puedes realizar esas pruebas. No necesitas conectar otro equipo "
            "ni entrar a Windows o al BIOS. Sin una revisión no puedo confirmar la causa ni un repuesto. "
            "Te recomiendo revisión presencial. Si quieres, puedes preguntar por el precio de un diagnóstico; "
            "no se ha reservado una cita."
        ))]}

    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        *state["messages"],
    ]

    try:
        # Última solicitud del usuario.
        user_text = next(
            (
                message.content.lower()
                for message in reversed(state["messages"])
                if message.type == "human"
                and isinstance(message.content, str)
            ),
            "",
        )

        # Identificar solicitudes de documentación.
        requests_documentation = any(
            word in user_text
            for word in (
                "documentación",
                "documentacion",
                "base de conocimiento",
                "procedimientos documentados",
            )
        )

        # Evitar consultar RAG repetidamente.
        rag_attempted = any(
            isinstance(message, ToolMessage)
            and message.name == "consultar_base_conocimiento"
            and message.status != "error"
            for message in state["messages"][state.get("turn_start_index", 0):]
        )

        if requests_documentation and not rag_attempted:
            response = _resolve_hardware_llm_rag().invoke(messages)
        else:
            response = _resolve_hardware_llm().invoke(messages)

        return {
            "messages": [response],
            "current_agent": "tecnico",
        }

    except Exception as e:
        error = (
            f"Error en el agente Técnico: "
            f"{type(e).__name__}"
        )

        return {
            "messages": [
                AIMessage(
                    content=(
                        "No fue posible completar el "
                        "diagnóstico técnico en este momento. "
                        "Inténtalo nuevamente más tarde."
                    )
                )
            ],
            "current_agent": "tecnico",
            "errors": state.get("errors", []) + [error],
        }


tecnico_node = hardware_node
