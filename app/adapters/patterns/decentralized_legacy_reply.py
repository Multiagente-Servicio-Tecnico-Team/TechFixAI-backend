"""Adaptador del patrón Red descentralizada (`app/agents/decentralized`).

Solo convierte respuestas previas; no construye grafos ni almacenamiento.
"""
from typing import Any

from langchain_core.messages import HumanMessage

from app.adapters.patterns.base import GraphPattern, last_message_text
from app.domain.chat import PatternReply, Quote, QuoteLine, TicketRef


class LegacyReplyPattern(GraphPattern):
    id = "decentralized"
    name = "Red descentralizada"
    supports_quotes = True


    def initial_state(self, customer_id: int, message: HumanMessage) -> dict[str, Any]:
        return {
            "messages": [message],
            "customer_id": customer_id,
            "conversation_id": "",
        }

    def prepare(self, graph: Any, state: dict[str, Any], config: dict[str, Any]) -> None:
        """Cada turno empieza con el control de transferencias reiniciado."""
        state["conversation_id"] = config["configurable"]["thread_id"]
        previous = graph.get_state(config).values
        state.update(
            turn_start_index=len(previous.get("messages", [])),
            handoff_count=0,
            handoff_history=[],
            tool_iterations={},
            errors=[],
            next_agent=None,
        )

    def to_reply(self, result: dict[str, Any]) -> PatternReply:
        quote_data = result.get("quote") or {}
        quote_status = result.get("quote_status")
        quote = None
        if (
            quote_status in {"proposed", "confirmed", "saved", "rejected"}
            and quote_data.get("total_amount") is not None
        ):
            if quote_data.get("quote_type") == "DIRECT_SALE":
                labor_label = "Mano de obra (venta directa)"
            elif quote_data.get("labor_task_type") == "diagnosis":
                labor_label = "DiagnÃ³stico tÃ©cnico"
            elif quote_data.get("labor_task_type") == "pc_build":
                labor_label = "Ensamble"
            else:
                labor_label = "Mano de obra"
            lines = []
            if quote_data.get("labor_cost"):
                lines.append(QuoteLine(labor_label, quote_data["labor_cost"]))
            lines.extend(
                QuoteLine(
                    f"{part['name']} × {part['quantity']}", part["subtotal"]
                )
                for part in quote_data.get("parts", [])
            )
            quote = Quote(
                status=quote_status,
                lines=lines,
                total=quote_data["total_amount"],
            )
        ticket_code = result.get("ticket_code")
        ticket = (
            TicketRef(
                code=ticket_code,
                status=result.get("ticket_status", "QUOTED"),
            )
            if (
                quote_status in {"confirmed", "saved"}
                and isinstance(ticket_code, str)
                and ticket_code
            )
            else None
        )
        return PatternReply(
            reply=last_message_text(result),
            quote=quote,
            ticket=ticket,
            pending_quote=quote_status == "proposed",
            quote_id=result.get("quote_id"),
        )
