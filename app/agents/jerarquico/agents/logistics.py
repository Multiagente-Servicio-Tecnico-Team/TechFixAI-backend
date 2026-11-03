from typing import Any, Literal

from langchain_core.messages import AIMessage, SystemMessage
from pydantic import BaseModel, Field

from app.agents.jerarquico.graph.state import ServiceState
from app.agents.jerarquico.trace import traced_tool
from app.application.logistics import record_customer_logistics_preference
from app.database.repository import ServiceRepository


class LogisticsDecision(BaseModel):
    mode: Literal["PHYSICAL_STORE", "COURIER_SHIPMENT", "unclear"]
    courier_company: str | None = Field(default=None, max_length=100)
    shipping_address: str | None = Field(default=None, max_length=500)


def make_logistics_agent(llm: Any, repository: ServiceRepository):
    def logistics_agent(state: ServiceState) -> dict[str, Any]:
        decision = llm.with_structured_output(LogisticsDecision).invoke(
            [
                SystemMessage(
                    content=(
                        "Eres el agente de logística. Interpreta únicamente la "
                        "modalidad que el cliente elige y, para courier, la empresa "
                        "y dirección de envío. No inventes datos de tienda, tarifas, "
                        "tracking ni fechas. Si falta un dato o no hay elección "
                        "inequívoca, usa mode=unclear."
                    )
                ),
                state["messages"][-1],
            ]
        )
        if decision.mode == "unclear":
            return {
                "awaiting_logistics": True,
                "outcome": "awaiting_logistics",
                "messages": [
                    AIMessage(
                        content=(
                            "¿Prefieres retiro presencial en tienda o envío por "
                            "courier? Para courier, indícame la empresa y la "
                            "dirección de entrega."
                        )
                    )
                ],
            }
        if decision.mode == "COURIER_SHIPMENT" and not (
            decision.courier_company and decision.shipping_address
        ):
            return {
                "awaiting_logistics": True,
                "outcome": "awaiting_logistics",
                "messages": [
                    AIMessage(
                        content=(
                            "Para registrar el envío por courier necesito el nombre "
                            "de la empresa y la dirección de entrega."
                        )
                    )
                ],
            }
        record_id = traced_tool(
            state,
            "logistics_record_write",
            lambda: record_customer_logistics_preference(
                repository,
                ticket_id=state["ticket_id"],
                customer_id=state["customer_id"],
                mode=decision.mode,
                courier_company=decision.courier_company,
                shipping_address=decision.shipping_address,
            ),
        )
        mode_label = (
            "retiro presencial" if decision.mode == "PHYSICAL_STORE" else "envío por courier"
        )
        return {
            "awaiting_logistics": False,
            "logistics_mode": decision.mode,
            "logistics_record_id": record_id,
            "outcome": "logistics_registered",
            "messages": [
                AIMessage(
                    content=(
                        f"Registré tu preferencia de {mode_label}. El registro "
                        "queda pendiente de recepción; esto no confirma que el "
                        "pedido haya sido pagado, reservado ni entregado."
                    )
                )
            ],
        }

    return logistics_agent
