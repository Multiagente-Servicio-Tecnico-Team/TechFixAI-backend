from app.agents.orquestador.graph.state import AgentState, PartRequest, TechnicalDiagnosis
from app.agents.orquestador.knowledge import retrieve_technical_knowledge
from app.config import create_chat_model
from app.settings import load_settings


TECHNICAL_SYSTEM_PROMPT = f"""
Eres el agente de soporte técnico de un taller. Responde todos los campos en español.
Emite un diagnóstico provisional,
no afirmes haber inspeccionado físicamente el equipo. Basa recomendaciones de
fallas y componentes en el contexto recuperado del catálogo técnico Markdown.
Ese catálogo es orientativo, no confirma la causa ni compatibilidad. La mano de obra tiene precios fijos configurados por tipo de tarea. Indica
labor_task_type="diagnosis" cuando no se conoce la causa exacta o se requiere
inspección y no propongas repuestos en ese caso. Indica
labor_task_type="maintenance" solo si el trabajo o cambio de componente ya está
determinado. No inventes precios, compatibilidad ni disponibilidad.
""".strip()


def tecnico_node(state: AgentState) -> dict[str, object]:
    model = create_chat_model().with_structured_output(TechnicalDiagnosis)
    passages = retrieve_technical_knowledge(
        f"{state.get('product', '')} {state.get('symptoms', '')} {state.get('category', '')}"
    )
    knowledge_context = "\n\n".join(passages) or "No hubo coincidencias en el catálogo Markdown."
    result = model.invoke(
        [
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
        if labor_task_type == "diagnosis"
        else [part.model_dump() for part in result.parts]
    )
    return {
        "diagnosis": result.diagnosis,
        "labor_task_type": labor_task_type,
        "labor_cost": load_settings().labor_price_for(labor_task_type),
        "requested_parts": required_parts,
    }