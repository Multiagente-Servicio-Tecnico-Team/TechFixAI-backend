"""Agente de logística del patrón Orquestador."""

from typing import Literal

from langchain_core.messages import AIMessage, SystemMessage
from pydantic import BaseModel, Field

from app.application.logistics import record_customer_logistics_preference
from app.application.prompts import build_system_prompt
from app.config import create_chat_model
from app.database.repository import ServiceRepository


class LogisticsDecision(BaseModel):
    mode: Literal["PHYSICAL_STORE", "COURIER_SHIPMENT", "unclear"]
    courier_company: str | None = Field(default=None, max_length=100)
    shipping_address: str | None = Field(default=None, max_length=500)


def logistics_node(state: dict[str, object]) -> dict[str, object]:
    repository = ServiceRepository()
    customer_id = state.get("user_id")
    if type(customer_id) is not int or type(state.get("ticket_id")) is not int:
        reply = "Necesito un ticket asociado a tu cuenta para registrar una preferencia logística."
        return {"logistics_pending": False, "response": reply,
                "messages": [AIMessage(content=reply)]}

    decision = create_chat_model().with_structured_output(LogisticsDecision).invoke([
        SystemMessage(content=build_system_prompt(role="CUSTOMER", pattern_id="orchestrator")),
        SystemMessage(content=(
            "Interpreta la preferencia explícita: retiro presencial o envío por courier. "
            "Para courier extrae empresa y dirección solo si están en el mensaje. "
            "Si falta elección o dato usa mode=unclear. No inventes tarifas ni plazos."
        )),
        *state.get("messages", []),
    ])
    if decision.mode == "unclear" or (decision.mode == "COURIER_SHIPMENT" and not (
        decision.courier_company and decision.shipping_address
    )):
        reply = "Indica retiro presencial o envío por courier; para courier necesito empresa y dirección."
        return {"logistics_pending": True, "response": reply,
                "messages": [AIMessage(content=reply)]}

    record_id = record_customer_logistics_preference(
        repository, customer_id=customer_id, ticket_id=int(state["ticket_id"]),
        mode=decision.mode, courier_company=decision.courier_company,
        shipping_address=decision.shipping_address,
    )
    reply = "Registré tu preferencia logística como pendiente de recepción; no confirma pago ni entrega."
    return {"logistics_pending": False, "logistics_record_id": record_id,
            "logistics_mode": decision.mode, "response": reply,
            "messages": [AIMessage(content=reply)]}
