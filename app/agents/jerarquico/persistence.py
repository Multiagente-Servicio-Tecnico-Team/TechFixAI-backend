from typing import Any

from app.agents.jerarquico.graph.state import ServiceState
from app.agents.jerarquico.trace import traced_tool
from app.database.repository import ServiceRepository

RECOMMENDED_PARTS_HEADER = "Repuestos o servicios recomendados (pendientes de verificar en almacén):"


def diagnosis_with_recommended_parts(diagnosis: str, required_parts: list[dict[str, Any]] | None) -> str:
    """Texto del diagnóstico que se guarda en el ticket.

    Si el técnico recomendó repuestos, se agregan como lista al final para que
    queden registrados aunque el cliente todavía no acepte la cotización. Sin
    repuestos, se guarda solo el diagnóstico.
    """
    text = diagnosis.strip()
    lines = []
    for part in required_parts or []:
        name = str(part.get("search_term", "")).strip()
        quantity = part.get("quantity", 1)
        if name:
            lines.append(f"- {name} × {quantity}")
    if not lines:
        return text
    return f"{text}\n\n{RECOMMENDED_PARTS_HEADER}\n" + "\n".join(lines)


def make_persist_diagnosis(repository: ServiceRepository):
    def persist_diagnosis(state: ServiceState) -> dict[str, Any]:
        ticket_id = state.get("ticket_id")
        customer_id = state.get("customer_id")
        if ticket_id is None or customer_id is None:
            raise ValueError("No se puede guardar el diagnóstico sin un ticket.")

        diagnosis = diagnosis_with_recommended_parts(
            state["provisional_diagnosis"], state.get("required_parts")
        )
        traced_tool(
            state,
            "ticket_diagnosis_write",
            lambda: repository.update_ticket_diagnosis(
                ticket_id=ticket_id,
                customer_id=customer_id,
                diagnosis=diagnosis,
                diagnosis_type=state["diagnosis_type"],
            ),
        )
        return {"ticket_status": "IN_DIAGNOSIS"}

    return persist_diagnosis
