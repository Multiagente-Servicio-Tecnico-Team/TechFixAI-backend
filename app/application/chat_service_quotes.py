"""Persist explicit customer acceptance of a service quote on its ticket."""

from decimal import Decimal
from typing import Any, Mapping

from app.application.quotes import calculate_quote
from app.domain.money import to_money


def accept_chat_service_quote(
    *,
    writer,
    customer_id: int,
    ticket_id: int,
    draft: Mapping[str, Any],
    payment_code: str,
) -> dict[str, object]:
    """Recalculate the chat draft, then let the repository revalidate live stock/prices."""
    if type(customer_id) is not int or customer_id < 1 or type(ticket_id) is not int or ticket_id < 1:
        raise ValueError("El cliente y el ticket deben venir de la sesión autenticada.")

    labor_cost = to_money(draft.get("labor_total"))
    task_type = draft.get("labor_task_type")
    parts = []
    seen: set[int] = set()
    for part in draft.get("parts", []):
        part_id = part.get("inventory_id", part.get("id", part.get("spare_part_id")))
        quantity = part.get("quantity")
        if type(part_id) is not int or part_id < 1 or type(quantity) is not int or quantity < 1 or part_id in seen:
            raise ValueError("La cotización contiene repuestos inválidos o repetidos.")
        seen.add(part_id)
        parts.append({
            **part,
            "id": part_id,
            "quantity": quantity,
            "unit_price": to_money(part.get("unit_price")),
            "subtotal": to_money(part.get("subtotal")),
        })

    calculated = calculate_quote(labor_cost=labor_cost, labor_task_type=task_type, parts=parts)
    if (to_money(draft.get("known_parts_subtotal")) != calculated["parts_cost"]
            or to_money(draft.get("total")) != calculated["total_amount"]):
        raise ValueError("La cotización cambió desde que se mostró al cliente.")

    observations = "Cotización de servicio aceptada explícitamente por el cliente desde chat."
    if isinstance(draft.get("observations"), str) and draft["observations"].strip():
        observations += " " + draft["observations"].strip()[:1500]
    return writer.accept_ticket_quote(
        ticket_id=ticket_id,
        customer_id=customer_id,
        quote_type="REPAIR",
        labor_cost=calculated["labor_cost"],
        parts_cost=calculated["parts_cost"],
        total_amount=calculated["total_amount"],
        observations=observations,
        parts=calculated["parts"],
        payment_code=payment_code,
    )
