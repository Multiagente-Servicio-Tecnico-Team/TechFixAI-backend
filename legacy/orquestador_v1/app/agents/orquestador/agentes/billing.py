"""Agente de facturación: persiste cotizaciones de servicio y acepta ventas."""

from langchain_core.messages import AIMessage

from app.agents.orquestador.agentes.ventas import persistencia_node
from app.config import CURRENCY_SYMBOL


def billing_agent_node(state):
    if not state.get("billing_pending"):
        result = persistencia_node(state)
        return {**result, "billing_flow": "SERVICE_QUOTE"}

    quote_id = state.get("sales_quote_id")
    customer_id = state.get("user_id")
    decision = state.get("sales_quote_decision")
    if (type(quote_id) is not int or quote_id < 1
            or type(customer_id) is not int or customer_id < 1
            or decision not in {"ACCEPT", "REJECT"}):
        response = "No pude recuperar la cotización pendiente. Vuelve a solicitarla para crear una propuesta nueva."
        return {
            "billing_pending": False,
            "sales_quote_decision": None,
            "awaiting_sales_quote_confirmation": False,
            "sales_quote_status": "UNAVAILABLE",
            "pc_build_selected": False,
            "billing_flow": "DIRECT_SALE",
            "response": response,
            "messages": [AIMessage(content=response)],
        }

    from app.adapters.persistence.sales_quotes import SalesQuoteRepositoryAdapter

    quotes = SalesQuoteRepositoryAdapter()
    if decision == "ACCEPT":
        accepted = None
        try:
            accepted = quotes.accept_direct_sales_quote(
                quote_id=quote_id,
                customer_id=customer_id,
                actor_user_id=None,
                idempotency_key=f"orchestrator-chat-{quote_id}",
                confirmation_channel="CHAT",
            )
        except (LookupError, ValueError, PermissionError):
            try:
                quotes.resolve_direct_sales_quote(
                    quote_id=quote_id,
                    customer_id=customer_id,
                    actor_user_id=None,
                    target_status="CANCELLED",
                    notes="Cotización de venta no aceptable por cambios de disponibilidad.",
                )
                status = "CANCELLED"
            except (LookupError, ValueError, PermissionError):
                status = "UNAVAILABLE"
            response = (
                "No pude aceptar la cotización porque el stock o su vigencia cambió. "
                "No reservé artículos; solicita una cotización actualizada."
            )
        else:
            status = accepted.get("status", "UNAVAILABLE")
            if accepted.get("error"):
                response = str(accepted["error"])
            else:
                kind = state.get("sales_quote_kind", "DIRECT_SALE")
                response = (
                    f"Aceptaste la cotización {kind} #{quote_id}. Reservé los artículos "
                    f"hasta su vencimiento. El pago {accepted.get('payment_code')} por "
                    f"{CURRENCY_SYMBOL} {state.get('build_total', 0):.2f} está pendiente; "
                    "no se creó un ticket de servicio."
                )
        return {
            "billing_pending": False,
            "sales_quote_decision": None,
            "awaiting_sales_quote_confirmation": False,
            "sales_quote_status": status,
            "sales_payment_code": accepted.get("payment_code")
            if accepted and not accepted.get("error") else None,
            "pc_build_selected": False,
            "billing_flow": "DIRECT_SALE",
            "response": response,
            "messages": [AIMessage(content=response)],
        }

    try:
        result = quotes.resolve_direct_sales_quote(
            quote_id=quote_id,
            customer_id=customer_id,
            actor_user_id=None,
            target_status="REJECTED",
            notes="Rechazada explícitamente en el chat.",
        )
    except (LookupError, ValueError, PermissionError):
        status = "UNAVAILABLE"
        response = "No pude actualizar esa cotización. No se hizo ningún cambio; consulta su estado antes de continuar."
    else:
        status = result.get("status", "REJECTED")
        response = "De acuerdo. Rechacé la cotización; no reservé inventario ni registré un pago."
    return {
        "billing_pending": False,
        "sales_quote_decision": None,
        "awaiting_sales_quote_confirmation": False,
        "sales_quote_status": status,
        "pc_build_selected": False,
        "billing_flow": "DIRECT_SALE",
        "response": response,
        "messages": [AIMessage(content=response)],
    }
