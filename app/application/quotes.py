from decimal import Decimal
import re
import unicodedata
from typing import Any, Mapping

from app.domain.money import to_money
from app.application.ports import AcceptedQuoteWriter, QuoteDraft
from app.domain.errors import StaleQuote

VALID_TASKS = {"maintenance", "diagnosis", "sale", "pc_build"}
MAX_QUOTE_TOTAL = Decimal("99999999.99")


def _quote_fingerprint(quote: QuoteDraft | Mapping[str, Any]) -> tuple[Any, ...]:
    if isinstance(quote, QuoteDraft):
        return (
            quote.ticket_id, quote.quote_type, quote.labor_task_type,
            quote.labor_cost, quote.parts_cost, quote.total_amount,
            tuple((line.item_id, line.quantity, line.unit_price, line.subtotal) for line in quote.lines),
        )
    parts = tuple(sorted(
        (
            str(part.get("code", part.get("id", ""))),
            int(part["quantity"]),
            to_money(part["unit_price"]),
            part.get("current_stock"),
            to_money(part.get("subtotal", part["unit_price"] * int(part["quantity"]))),
        )
        for part in quote.get("parts", [])
    ))
    return (
        quote.get("ticket_id"), quote.get("quote_type", "REPAIR"),
        quote.get("labor_task_type"), to_money(quote.get("labor_cost", 0)),
        to_money(quote.get("parts_cost", 0)), to_money(quote.get("total_amount", 0)),
        parts,
    )


def quote_changed(
    previous: QuoteDraft | Mapping[str, Any],
    current: QuoteDraft | Mapping[str, Any],
) -> bool:
    """Repricing is required if any server-calculated quote field changed."""
    return _quote_fingerprint(previous) != _quote_fingerprint(current)


def interpret_quote_decision(message: str) -> str | None:
    """Accept/reject only an explicit, standalone customer decision."""
    normalized = unicodedata.normalize("NFKD", message.casefold())
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized).strip()
    accept = {
        "si", "si confirmo", "confirmo", "confirmar", "si autorizo",
        "de acuerdo", "acepto", "acepto la cotizacion", "si acepto", "correcto",
    }
    reject = {
        "no", "no gracias", "no rechazo", "cancelo", "cancelar", "rechazo", "rechazar",
        "rechazo la cotizacion", "no acepto",
    }
    if normalized in accept:
        return "ACCEPT"
    if normalized in reject:
        return "REJECT"
    return None


def calculate_quote(
    *, labor_cost: Decimal | str | int,
    labor_task_type: str,
    parts: list[dict[str, Any]],
) -> dict[str, Any]:
    if labor_task_type not in VALID_TASKS:
        raise ValueError(f"Tipo de mano de obra no reconocido: {labor_task_type}.")
    labor = to_money(labor_cost)
    if labor < 0 or (labor_task_type != "sale" and labor == 0):
        raise ValueError("La mano de obra debe tener un importe fijo válido.")
    lines = []
    for part in parts:
        quantity = part.get("quantity")
        if type(quantity) is not int or quantity < 1:
            raise ValueError("Cada artículo debe tener una cantidad entera positiva.")
        unit_price = to_money(part.get("unit_price"))
        if unit_price <= 0:
            raise ValueError("Cada artículo debe tener un precio positivo validado.")
        subtotal = to_money(unit_price * quantity)
        lines.append({**part, "unit_price": unit_price, "subtotal": subtotal})
    parts_cost = sum((line["subtotal"] for line in lines), Decimal("0.00"))
    total = to_money(labor + parts_cost)
    if total > MAX_QUOTE_TOTAL:
        raise ValueError("El importe excede el límite del esquema de cotizaciones.")
    return {
        "labor_task_type": labor_task_type,
        "labor_cost": labor,
        "parts_cost": parts_cost,
        "total_amount": total,
        "parts": lines,
    }


def accept_quoted_draft(
    *,
    writer: AcceptedQuoteWriter,
    customer_id: int,
    ticket_id: int,
    quote_type: str,
    draft: Mapping[str, Any],
    observations: str,
    payment_code: str,
) -> dict[str, object]:
    """Validate quote arithmetic before asking the repository to persist acceptance."""
    if type(customer_id) is not int or customer_id < 1 or type(ticket_id) is not int or ticket_id < 1:
        raise ValueError("La identidad del cliente y el ticket deben venir del servidor.")
    calculated = calculate_quote(
        labor_cost=draft["labor_cost"],
        labor_task_type=draft["labor_task_type"],
        parts=list(draft.get("parts", [])),
    )
    persisted_candidate = {
        **calculated,
        "ticket_id": draft.get("ticket_id"),
        "quote_type": quote_type,
    }
    if quote_changed(draft, persisted_candidate):
        raise StaleQuote()
    return writer.accept_ticket_quote(
        ticket_id=ticket_id,
        customer_id=customer_id,
        quote_type=quote_type,
        labor_cost=calculated["labor_cost"],
        parts_cost=calculated["parts_cost"],
        total_amount=calculated["total_amount"],
        observations=observations,
        parts=calculated["parts"],
        payment_code=payment_code,
    )
