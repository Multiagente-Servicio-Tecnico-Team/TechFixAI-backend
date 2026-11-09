from typing import Any
from uuid import uuid4

from langchain_core.messages import AIMessage

from app.agents.jerarquico.graph.state import ServiceState
from app.agents.jerarquico.trace import traced_tool
from app.application.quotes import accept_quoted_draft
from app.database.repository import ServiceRepository


def make_billing_agent(repository: ServiceRepository):
    def billing_agent(state: ServiceState) -> dict[str, Any]:
        quote = state["quote"]
        if state.get("request_type") in {"SALE", "PC_BUILD"}:
            from app.adapters.persistence.sales_quotes import SalesQuoteRepositoryAdapter

            accepted = traced_tool(
                state,
                "direct_sale_quote_acceptance",
                lambda: SalesQuoteRepositoryAdapter().accept_direct_sales_quote(
                    quote_id=int(state["quote_id"]),
                    customer_id=int(state["customer_id"]),
                    actor_user_id=None,
                    idempotency_key=f"chat-sale-quote-{int(state['quote_id'])}",
                ),
            )
            return {
                "quote_id": accepted["quote_id"],
                "payment_id": accepted["payment_id"],
                "payment_code": accepted["payment_code"],
                "payment_status": "PENDING",
                "ticket_id": None,
                "ticket_code": "",
                "ticket_status": None,
                "awaiting_quote_confirmation": False,
                "awaiting_logistics": False,
                "outcome": "direct_sale_accepted",
                "messages": [AIMessage(content=(
                    f"Aceptaste la cotización de venta #{accepted['quote_id']}. "
                    f"Reservé el stock hasta su vencimiento. El pago {accepted['payment_code']} "
                    f"por S/ {quote['total_amount']:.2f} está PENDIENTE; el pedido se creará "
                    "cuando ADMIN confirme que recibió el pago. No se creó un ticket de reparación."
                ))],
            }
        accepted_quote = traced_tool(
            state,
            "accepted_quote_write",
            lambda: accept_quoted_draft(
                writer=repository,
                ticket_id=state["ticket_id"],
                customer_id=state["customer_id"],
                quote_type=state["quote_type"],
                draft=quote,
                observations=(
                    "Cotización aceptada explícitamente por el cliente. "
                    f"Tipo de mano de obra: {quote['labor_task_type']}. "
                    f"Costo fijo de mano de obra: S/ {quote['labor_cost']:.2f}. "
                    "El inventario no se reserva ni descuenta automáticamente."
                ),
                payment_code=f"PAY-{uuid4().hex[:12].upper()}",
            ),
        )
        return {
            "quote_id": accepted_quote["quote_id"],
            "payment_id": accepted_quote["payment_id"],
            "payment_code": accepted_quote["payment_code"],
            "ticket_status": "PAYMENT_PENDING",
            "awaiting_quote_confirmation": False,
            "awaiting_logistics": True,
            "outcome": "quoted",
            "messages": [
                AIMessage(
                    content=(
                        f"La cotización aceptada quedó registrada para el ticket "
                        f"{state['ticket_code']}. El pago {accepted_quote['payment_code']} "
                        f"por S/ {quote['total_amount']:.2f} está PENDIENTE; no "
                        "confirma que el pago haya sido recibido. ¿Prefieres retiro "
                        "presencial en tienda o envío por courier?"
                    )
                )
            ],
        }

    return billing_agent
