from typing import Any

from app.agents.jerarquico.graph.state import ServiceState
from app.agents.jerarquico.trace import traced_tool
from app.database.repository import ServiceRepository


def make_persist_diagnosis(repository: ServiceRepository):
    def persist_diagnosis(state: ServiceState) -> dict[str, Any]:
        ticket_id = state.get("ticket_id")
        customer_id = state.get("customer_id")
        if ticket_id is None or customer_id is None:
            raise ValueError("No se puede guardar el diagnóstico sin un ticket.")

        traced_tool(
            state,
            "ticket_diagnosis_write",
            lambda: repository.update_ticket_diagnosis(
                ticket_id=ticket_id,
                customer_id=customer_id,
                diagnosis=state["provisional_diagnosis"],
                diagnosis_type=state["diagnosis_type"],
            ),
        )
        return {"ticket_status": "IN_DIAGNOSIS"}

    return persist_diagnosis
