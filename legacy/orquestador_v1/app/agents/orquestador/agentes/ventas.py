from decimal import Decimal
from uuid import uuid4

from langchain_core.messages import AIMessage

from app.agents.orquestador.graph.state import AgentState
from app.application.catalog import CatalogService
from app.application.quotes import calculate_quote as calculate_shared_quote
from app.application.quotes import quote_changed
from app.application.quotes import accept_quoted_draft
from app.config import CURRENCY_SYMBOL
from app.database.repository import ServiceRepository
from app.domain.errors import StaleQuote

sales_repository = ServiceRepository()
catalog_service = CatalogService(sales_repository)


def ventas_node(state: AgentState) -> dict[str, object]:
    inventory = state.get("inventory", [])
    available_parts = [part for part in inventory if part["available"]]
    unavailable_parts = [part for part in inventory if not part["available"]]
    labor_cost = Decimal(str(state.get("labor_cost", 0))).quantize(Decimal("0.01"))
    task_type = state.get("labor_task_type", "maintenance")
    calculated_quote = calculate_shared_quote(
        labor_cost=labor_cost,
        labor_task_type=task_type,
        parts=available_parts,
    )
    parts_total = calculated_quote["parts_cost"]
    total = calculated_quote["total_amount"]

    item_lines = [
        f"- {part['name']} x{part['quantity']}: "
        f"{CURRENCY_SYMBOL} {Decimal(str(part['unit_price'])) * int(part['quantity']):,.2f}"
        for part in available_parts
    ]
    if unavailable_parts:
        item_lines.extend(
            f"- {part['requested_name']}: sin existencias suficientes "
            f"(solicitadas {part['quantity']}, disponibles {part['stock']})"
            for part in unavailable_parts
        )
    detail = "\n".join(item_lines) if item_lines else "- No se requieren repuestos"
    response = (
        "Resumen del caso:\n"
        f"- Solicitud: {state['category']}\n"
        f"- Equipo: {state['product']}\n"
        f"- Falla descrita: {state['symptoms']}\n\n"
        f"Diagnóstico provisional: {state['diagnosis']}\n\n"
        "Cotización de servicio (todavía no guardada):\n"
        f"- Mano de obra: {CURRENCY_SYMBOL} {labor_cost:,.2f}\n"
        f"{detail}\n"
        f"- Repuestos disponibles: {CURRENCY_SYMBOL} {parts_total:,.2f}\n"
        f"- Total: {CURRENCY_SYMBOL} {total:,.2f}\n\n"
        "La evaluación es estimada y debe confirmarse tras revisar físicamente el equipo.\n\n"
        f"El ticket {state.get('ticket_code', '')} ya está registrado para seguimiento.\n\n"
        "¿Aceptas que guarde esta cotización en el ticket? Responde **Sí, confirmo** o **No**."
    )
    return {
        "available_parts": available_parts,
        "parts_total": parts_total,
        "total": total,
        "quote_preview_ready": True,
        "awaiting_ticket_confirmation": True,
        "ticket_confirmed": False,
        "response": response,
        "messages": [AIMessage(content=response)],
    }


def persistencia_node(state: AgentState) -> dict[str, object]:
    ticket_id = state.get("ticket_id")
    customer_id = state.get("user_id")
    if type(ticket_id) is not int or ticket_id < 1 or type(customer_id) is not int or customer_id < 1:
        raise ValueError("Se requiere el ticket de servicio y el cliente autenticado para guardar la cotización.")

    available_parts = list(state.get("available_parts", []))
    refreshed_parts = []
    for quoted_part in available_parts:
        code = quoted_part.get("code")
        current = catalog_service.find_by_code(code) if isinstance(code, str) else None
        if current is None:
            response = "Un producto de la propuesta ya no está disponible. El ticket se conserva; no guardé la cotización ni registré un pago."
            return {
                "ticket_confirmed": False,
                "awaiting_ticket_confirmation": False,
                "ticket_id": ticket_id,
                "ticket_code": state.get("ticket_code"),
                "ticket_status": state.get("ticket_status", "IN_DIAGNOSIS"),
                "response": response,
                "messages": [AIMessage(content=response)],
            }
        quantity = int(quoted_part["quantity"])
        stock = int(current["current_stock"])
        if stock < quantity:
            response = (
                f"El stock de {current['name']} cambió y ahora es insuficiente. "
                "El ticket se conserva; no guardé la cotización ni registré un pago."
            )
            return {
                "ticket_confirmed": False,
                "awaiting_ticket_confirmation": False,
                "ticket_id": ticket_id,
                "ticket_code": state.get("ticket_code"),
                "ticket_status": state.get("ticket_status", "IN_DIAGNOSIS"),
                "response": response,
                "messages": [AIMessage(content=response)],
            }
        refreshed_parts.append({
            **current,
            "quantity": quantity,
            "stock": stock,
            "current_stock": stock,
            "available": True,
        })

    task_type = state.get("labor_task_type", "maintenance")
    refreshed_quote = calculate_shared_quote(
        labor_cost=state["labor_cost"],
        labor_task_type=task_type,
        parts=refreshed_parts,
    )
    previous_quote = {
        "quote_type": "REPAIR",
        "labor_task_type": task_type,
        "labor_cost": state["labor_cost"],
        "parts_cost": state["parts_total"],
        "total_amount": state["total"],
        "parts": available_parts,
    }
    current_quote = {"quote_type": "REPAIR", **refreshed_quote}
    if quote_changed(previous_quote, current_quote):
        response = (
            "El precio o la disponibilidad cambió desde la propuesta. "
            f"El importe actualizado es {CURRENCY_SYMBOL} "
            f"{refreshed_quote['total_amount']:,.2f}. El ticket sigue abierto; "
            "revisa los valores y confirma de nuevo."
        )
        return {
            "available_parts": refreshed_parts,
            "parts_total": refreshed_quote["parts_cost"],
            "total": refreshed_quote["total_amount"],
            "ticket_confirmed": False,
            "awaiting_ticket_confirmation": True,
            "ticket_id": ticket_id,
            "ticket_code": state.get("ticket_code"),
            "ticket_status": state.get("ticket_status", "IN_DIAGNOSIS"),
            "response": response,
            "messages": [AIMessage(content=response)],
        }

    try:
        accepted = accept_quoted_draft(
            writer=sales_repository,
            ticket_id=ticket_id,
            customer_id=customer_id,
            quote_type="REPAIR",
            draft={"quote_type": "REPAIR", **refreshed_quote},
            observations=(
                "Cotización de servicio aceptada explícitamente por el cliente desde chat. "
                f"Diagnóstico provisional: {state['diagnosis']}"
            ),
            payment_code=f"PAY-{uuid4().hex[:12].upper()}",
        )
    except StaleQuote:
        response = (
            "El precio o el stock cambió justo antes de guardar. No se registró la cotización "
            "ni el pago. Vuelve a consultar los artículos para preparar una propuesta actualizada."
        )
        return {
            "ticket_id": ticket_id,
            "ticket_code": state.get("ticket_code"),
            "ticket_status": state.get("ticket_status", "IN_DIAGNOSIS"),
            "ticket_confirmed": False,
            "awaiting_ticket_confirmation": False,
            "response": response,
            "messages": [AIMessage(content=response)],
        }

    response = (
        f"Guardé la cotización aceptada #{accepted['quote_id']} en el ticket "
        f"{state['ticket_code']} por {CURRENCY_SYMBOL} "
        f"{refreshed_quote['total_amount']:,.2f}. El pago {accepted['payment_code']} "
        "está pendiente; aún no se recibió el pago ni se reservó inventario."
    )
    return {
        "ticket_id": ticket_id,
        "ticket_code": state["ticket_code"],
        "quote_id": accepted["quote_id"],
        "payment_code": accepted["payment_code"],
        "ticket_status": "PAYMENT_PENDING",
        "payment_status": accepted["payment_status"],
        "ticket_confirmed": False,
        "awaiting_ticket_confirmation": False,
        "response": response,
        "messages": [AIMessage(content=response)],
    }
