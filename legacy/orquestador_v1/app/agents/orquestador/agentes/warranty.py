"""Agente de garantía del patrón Orquestador."""

from uuid import uuid4

from langchain_core.messages import AIMessage

from app.application.tickets import lookup_customer_ticket
from app.application.warranties import (
    lookup_customer_warranty,
    register_customer_warranty_claim,
)
from app.database.repository import ServiceRepository


def new_claim_code() -> str:
    return f"CLM-{uuid4().hex[:12].upper()}"


def warranty_node(state: dict[str, object]) -> dict[str, object]:
    repository = ServiceRepository()
    customer_id = state.get("user_id")
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

    ticket_code = str(state.get("ticket_code", ""))
    ticket = lookup_customer_ticket(
        repository, customer_id=customer_id, ticket_code=ticket_code
    ) if ticket_code else None
    if ticket is None:
        reply = "Para registrar el reclamo, indícame el código de un ticket de servicio asociado a tu cuenta."
        return {"warranty_claim_pending": True, "response": reply,
                "messages": [AIMessage(content=reply)]}

    reason = next((str(message.content).strip()
                   for message in reversed(state.get("messages", []))
                   if getattr(message, "type", None) == "human"), "")
    claim = register_customer_warranty_claim(
        repository, customer_id=customer_id, ticket_id=int(ticket["id"]),
        warranty_code=str(state["warranty_code"]), reason=reason,
        claim_code=new_claim_code(),
    )
    reply = (f"Registré el reclamo {claim['claim_code']} para revisión manual. "
             "La cobertura final depende de la evaluación del equipo.")
    return {"warranty_claim_pending": False, "warranty_id": claim["warranty_id"],
            "warranty_claim_code": claim["claim_code"],
            "ticket_status": claim["ticket_status"], "response": reply,
            "messages": [AIMessage(content=reply)]}
