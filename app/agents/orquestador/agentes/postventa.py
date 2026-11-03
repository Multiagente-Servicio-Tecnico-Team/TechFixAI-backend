"""Warranty and logistics node used by the Orchestrator topology."""

from typing import Literal
from uuid import uuid4

from langchain_core.messages import AIMessage, SystemMessage
from pydantic import BaseModel, Field

from app.application.logistics import record_customer_logistics_preference
from app.application.tickets import lookup_customer_ticket
from app.application.warranties import (
    lookup_customer_warranty,
    register_customer_warranty_claim,
)
from app.config import create_chat_model
from app.database.repository import ServiceRepository


class LogisticsDecision(BaseModel):
    mode: Literal["PHYSICAL_STORE", "COURIER_SHIPMENT", "unclear"]
    courier_company: str | None = Field(default=None, max_length=100)
    shipping_address: str | None = Field(default=None, max_length=500)


def new_claim_code() -> str:
    return f"CLM-{uuid4().hex[:12].upper()}"


def postventa_node(state: dict[str, object]) -> dict[str, object]:
    repository = ServiceRepository()
    customer_id = state.get("user_id")
    if state.get("warranty_status_pending") or state.get("warranty_claim_pending"):
        warranty = lookup_customer_warranty(
            repository,
            customer_id=customer_id,
            warranty_code=str(state.get("warranty_code", "")),
        )
        if warranty is None:
            reply = "No encontré una póliza con ese código asociada a tu cuenta."
            return {"warranty_status_pending": False, "warranty_claim_pending": False,
                    "response": reply, "messages": [AIMessage(content=reply)]}
        end_date = warranty["end_date"]
        date_text = end_date.isoformat() if hasattr(end_date, "isoformat") else str(end_date)[:10]
        if state.get("warranty_status_pending"):
            valid = warranty.get("status") == "ACTIVE" and warranty.get("not_expired")
            status_text = "vigente" if valid else "no vigente"
            reply = (f"La póliza {warranty['warranty_code']} figura como {status_text} "
                     f"para {warranty['item_or_service_name']}. Vence el {date_text}.")
            return {"warranty_status_pending": False, "warranty_status": warranty["status"],
                    "response": reply, "messages": [AIMessage(content=reply)]}
        if warranty.get("status") != "ACTIVE" or not warranty.get("not_expired"):
            reply = "La póliza no está vigente; no registré un reclamo."
            return {"warranty_claim_pending": False, "response": reply,
                    "messages": [AIMessage(content=reply)]}
        ticket = None
        ticket_code = str(state.get("ticket_code", ""))
        if ticket_code:
            ticket = lookup_customer_ticket(
                repository, customer_id=customer_id, ticket_code=ticket_code
            )
        if ticket is None:
            reply = "Para registrar el reclamo, indícame el código de un ticket de servicio asociado a tu cuenta."
            return {"warranty_claim_pending": True, "response": reply,
                    "messages": [AIMessage(content=reply)]}
        reason = next((str(m.content).strip() for m in reversed(state.get("messages", []))
                       if getattr(m, "type", None) == "human"), "")
        claim = register_customer_warranty_claim(
            repository, customer_id=customer_id, ticket_id=int(ticket["id"]),
            warranty_code=str(state["warranty_code"]), reason=reason,
            claim_code=new_claim_code(),
        )
        reply = (f"Registré el reclamo {claim['claim_code']} para revisión manual. "
                 "La cobertura final depende de la evaluación del equipo.")
        return {"warranty_claim_pending": False, "warranty_id": claim["warranty_id"],
                "warranty_claim_code": claim["claim_code"], "ticket_status": claim["ticket_status"],
                "response": reply, "messages": [AIMessage(content=reply)]}

    if state.get("logistics_pending"):
        if type(customer_id) is not int or type(state.get("ticket_id")) is not int:
            reply = "Necesito un ticket asociado a tu cuenta para registrar una preferencia logística."
            return {"logistics_pending": False, "response": reply,
                    "messages": [AIMessage(content=reply)]}
        decision = create_chat_model().with_structured_output(LogisticsDecision).invoke([
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

    return {}
