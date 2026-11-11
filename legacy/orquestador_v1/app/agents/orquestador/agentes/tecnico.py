from app.agents.orquestador.graph.state import AgentState, PartRequest, TechnicalDiagnosis
from app.agents.orquestador.knowledge import retrieve_technical_knowledge
from app.config import create_chat_model
from app.settings import load_settings
from app.application.prompts import build_system_prompt


TECHNICAL_SYSTEM_PROMPT = """
Responde todos los campos en español y emite un diagnóstico provisional; no afirmes
haber inspeccionado físicamente el equipo. Basa las recomendaciones en el contexto
recuperado del catálogo técnico Markdown. El catálogo es orientativo y no confirma
causa ni compatibilidad. La mano de obra tiene precios fijos configurados por tipo
de tarea. Usa labor_task_type="diagnosis" si la causa exacta no se conoce o se
requiere inspección, y no propongas repuestos en ese caso. Usa
labor_task_type="maintenance" solo si el trabajo o cambio de componente ya está
determinado. No inventes precios, compatibilidad ni disponibilidad.
""".strip()


def technical_support_node(state: AgentState, *, mode: str = "hardware") -> dict[str, object]:
    if mode not in {"hardware", "software"}:
        raise ValueError("La especialidad técnica no es válida.")
    model = create_chat_model().with_structured_output(TechnicalDiagnosis)
    passages = retrieve_technical_knowledge(
        f"{state.get('product', '')} {state.get('symptoms', '')} {state.get('category', '')}"
    )
    knowledge_context = "\n\n".join(passages) or "No hubo coincidencias en el catálogo Markdown."
    specialist_prompt = (
        "Eres especialista en sistemas operativos, aplicaciones, controladores y "
        "problemas lógicos. No diagnostiques fallas físicas, no solicites "
        "contraseñas, códigos de recuperación ni claves de licencia, y no "
        "recomiendes software pirata. Advierte sobre posible pérdida de datos "
        "antes de reinstalar o formatear y exige autorización explícita. No "
        "propongas repuestos de hardware para un caso exclusivamente de software."
        if mode == "software"
        else
        "Eres especialista en diagnóstico físico de hardware. No guíes al cliente "
        "a abrir fuentes, manipular baterías hinchadas, líquidos o circuitos. Si "
        "la evidencia apunta exclusivamente a software, indícalo como derivación "
        "y no presentes una falla física como confirmada."
    )
    result = model.invoke(
        [
            ("system", build_system_prompt(role="CUSTOMER", pattern_id="orchestrator")),
            ("system", specialist_prompt),
            ("system", TECHNICAL_SYSTEM_PROMPT),
            (
                "human",
                f"Equipo: {state.get('product', 'No especificado')}\n"
                f"Síntomas: {state.get('symptoms', '')}\n"
                f"Categoría: {state.get('category', '')}\n\n"
                f"Contexto recuperado del catálogo técnico local:\n{knowledge_context}",
            ),
        ]
    )
    labor_task_type = result.labor_task_type
    required_parts = (
        []
        if labor_task_type == "diagnosis" or mode == "software"
        else [part.model_dump() for part in result.parts]
    )
    return {
        "diagnosis": result.diagnosis,
        "diagnosis_type": (
            "HYBRID" if result.diagnosis_type == "HYBRID"
            else "SOFTWARE" if mode == "software"
            else "HARDWARE"
        ),
        "labor_task_type": labor_task_type,
        "labor_cost": load_settings().labor_price_for(labor_task_type),
        "requested_parts": required_parts,
    }


def tecnico_node(state: AgentState) -> dict[str, object]:
    """Compatibilidad histórica: este nodo representa soporte de hardware."""
    return technical_support_node(state, mode="hardware")
