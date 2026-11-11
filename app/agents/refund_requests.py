"""Shared conversation handler for safe, pending-only refund requests."""
from __future__ import annotations

import re
from decimal import Decimal
from typing import Any, Callable

from langchain_core.messages import AIMessage, HumanMessage

from app.application.refunds import request_refund
from app.domain.refunds import RefundEligibilityError

_DETAILS = re.compile(
    r"(?is)\b(PAY-[A-Z0-9-]{4,50})\b.*?"
    r"\bimporte\s*[:=]?\s*(?:S/\s*)?([0-9]+(?:[.,][0-9]{1,2})?).*?"
    r"\bmotivo\s*[:=]\s*(.{3,1000})\s*$"
)
TraceTool = Callable[[dict[str, Any], str, Callable[[], Any]], Any]


def make_refund_agent(repository: Any, *, trace_tool: TraceTool | None = None):
    def run_tool(state: dict[str, Any], name: str, operation: Callable[[], Any]):
        return trace_tool(state, name, operation) if trace_tool else operation()

    def refund_agent(state: dict[str, Any]) -> dict[str, Any]:
        message = next(
            (
                item.content.strip()
                for item in reversed(state.get("messages", []))
                if isinstance(item, HumanMessage) and isinstance(item.content, str)
            ),
            "",
        )
        match = _DETAILS.search(message)
        if not match:
            return {
                "current_agent": "reembolsos",
                "awaiting_refund_details": True,
                "route": "refund_request",
                "messages": [AIMessage(content=(
                    "Para registrar una solicitud pendiente, envía en un solo mensaje "
                    "el código de pago (PAY-…), el importe y el motivo. Ejemplo: "
                    "PAY-ABC123; importe: S/ 25.50; motivo: producto defectuoso. "
                    "El reembolso requiere revisión manual y este chat no ejecuta pagos."
                ))],
            }

        customer_id = state.get("customer_id", state.get("user_id"))
        if type(customer_id) is not int or customer_id < 1:
            return {
                "current_agent": "reembolsos",
                "awaiting_refund_details": True,
                "route": "refund_request",
                "messages": [AIMessage(content=(
                    "Para registrar la solicitud pendiente, inicia sesion como cliente y envia el codigo de pago, "
                    "importe y motivo. No se consulto ni modifico ningun pago."
                ))],
            }
        payment_code, amount, reason = match.groups()
        try:
            payment_id = run_tool(
                state,
                "refund_payment_lookup",
                lambda: repository.find_payment_id_by_code(customer_id, payment_code),
            )
            if payment_id is None:
                raise ValueError("No se pudo validar ese pago para esta cuenta.")
            request = run_tool(
                state,
                "refund_request_write",
                lambda: request_refund(
                    repository,
                    customer_id=customer_id,
                    payment_id=payment_id,
                    amount=Decimal(amount.replace(",", ".")),
                    reason=reason.strip(),
                ),
            )
        except (ValueError, RefundEligibilityError) as exc:
            return {
                "current_agent": "reembolsos",
                "awaiting_refund_details": True,
                "route": "refund_request",
                "messages": [AIMessage(content=(
                    f"No pude registrar la solicitud: {exc} No se realizó ningún "
                    "reembolso. Verifica el código, el importe y el motivo."
                ))],
            }
        return {
            "current_agent": "reembolsos",
            "awaiting_refund_details": False,
            "refund_id": request.id,
            "refund_status": request.status,
            "route": "refund_request",
            "outcome": "refund_requested",
            "messages": [AIMessage(content=(
                f"Registré la solicitud {request.id} por S/ {request.amount:.2f} "
                "con estado pendiente de revisión manual. No se ejecutó ningún pago "
                "ni se modificó el saldo."
            ))],
        }

    return refund_agent
