from decimal import Decimal
from uuid import uuid4

from langchain_core.messages import AIMessage

from app.agents.orquestador.agentes.quotes import calculate_quote
from app.agents.orquestador.graph.state import AgentState
from app.application.catalog import CatalogService
from app.application.quotes import calculate_quote as calculate_shared_quote
from app.application.quotes import quote_changed
from app.config import CURRENCY_SYMBOL
from app.database.repository import ServiceRepository

sales_repository = ServiceRepository()
catalog_service = CatalogService(sales_repository)


def ventas_node(state: AgentState) -> dict[str, object]:
    inventory = state.get("inventory", [])
    available_parts = [part for part in inventory if part["available"]]
    unavailable_parts = [part for part in inventory if not part["available"]]
    labor_cost = Decimal(str(state.get("labor_cost", 0))).quantize(Decimal("0.01"))
    parts_total, total = calculate_quote(labor_cost, available_parts)

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
        "Presupuesto sugerido (todavía no guardado):\n"
        f"- Mano de obra: {CURRENCY_SYMBOL} {labor_cost:,.2f}\n"
        f"{detail}\n"
        f"- Repuestos disponibles: {CURRENCY_SYMBOL} {parts_total:,.2f}\n"
        f"- Total: {CURRENCY_SYMBOL} {total:,.2f}\n\n"
        "La evaluación es estimada y debe confirmarse tras revisar físicamente el equipo.\n\n"
        "¿Confirmas que guarde el ticket y este presupuesto? Responde **Sí, confirmo** o **No**."
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
    available_parts = list(state.get("available_parts", []))
    refreshed_parts = []
    for quoted_part in available_parts:
        code = quoted_part.get("code")
        current = catalog_service.find_by_code(code) if isinstance(code, str) else None
        if current is None:
            return {
                "ticket_confirmed": False,
                "awaiting_ticket_confirmation": False,
                "ticket_cancelled": True,
                "response": "Un producto de la propuesta ya no está disponible en el catálogo; no guardé el ticket.",
                "messages": [AIMessage(content="Un producto de la propuesta ya no está disponible en el catálogo; no guardé el ticket.")],
            }
        quantity = int(quoted_part["quantity"])
        stock = int(current["current_stock"])
        if stock < quantity:
            response = (
                f"El stock de {current['name']} cambió y ahora es insuficiente. "
                "No guardé el ticket ni el presupuesto."
            )
            return {
                "ticket_confirmed": False,
                "awaiting_ticket_confirmation": False,
                "ticket_cancelled": True,
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
            f"{refreshed_quote['total_amount']:,.2f}. "
            "No he guardado el ticket; revisa los valores y confirma de nuevo."
        )
        return {
            "available_parts": refreshed_parts,
            "parts_total": refreshed_quote["parts_cost"],
            "total": refreshed_quote["total_amount"],
            "ticket_confirmed": False,
            "awaiting_ticket_confirmation": True,
            "response": response,
            "messages": [AIMessage(content=response)],
        }

    accepted = sales_repository.create_accepted_ticket_quote(
        customer_id=state["user_id"],
        request_type="REPAIR",
        quote_type="REPAIR",
        title=f"{state['product']} - {state['category']}",
        failure_description=state["symptoms"],
        provisional_diagnosis=state["diagnosis"],
        diagnosis_type="HARDWARE",
        labor_cost=Decimal(str(state["labor_cost"])),
        parts_cost=refreshed_quote["parts_cost"],
        total_amount=refreshed_quote["total_amount"],
        observations=state["diagnosis"],
        parts=refreshed_parts,
        payment_code=f"PAY-{uuid4().hex[:12].upper()}",
    )
    if accepted["total_amount"] != state["total"]:
        raise RuntimeError("El presupuesto persistido no coincide con la vista previa")
    response = (
        f"Guard? el ticket {accepted['ticket_code']} y la cotizaci?n aceptada "
        f"#{accepted['quote_id']} por {CURRENCY_SYMBOL} "
        f"{accepted['total_amount']:,.2f}. El pago {accepted['payment_code']} "
        "est? pendiente; a?n no se recibi? el pago ni se reserv? inventario."
    )
    return {
        "ticket_id": accepted["ticket_id"],
        "ticket_code": accepted["ticket_code"],
        "quote_id": accepted["quote_id"],
        "payment_code": accepted["payment_code"],
        "ticket_status": "PAYMENT_PENDING",
        "payment_status": accepted["payment_status"],
        "response": response,
        "messages": [AIMessage(content=response)],
    }
