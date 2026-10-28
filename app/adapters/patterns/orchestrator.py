"""Adaptador del patrón Orquestador / supervisor (`app/agents/orquestador`)."""
from typing import Any

from langchain_core.messages import HumanMessage

from app.adapters.patterns.base import GraphPattern, last_message_text
from app.domain.chat import PatternReply, Quote, QuoteLine, TicketRef


class OrchestratorPattern(GraphPattern):
    id = "orchestrator"
    name = "Orquestador / supervisor"

    def build_graph(self) -> Any:
        from app.agents.orquestador import build_graph

        return build_graph()

    def initial_state(self, customer_id: int, message: HumanMessage) -> dict[str, Any]:
        return {"messages": [message], "user_id": customer_id}

    def to_reply(self, result: dict[str, Any]) -> PatternReply:
        response = result.get("response")
        text = response if isinstance(response, str) and response.strip() else last_message_text(result)
        return PatternReply(
            reply=text,
            quote=self.quote(result),
            ticket=self.ticket(result),
            pending_quote=bool(result.get("awaiting_ticket_confirmation")),
        )

    @staticmethod
    def quote(result: dict[str, Any]) -> Quote | None:
        if result.get("awaiting_ticket_confirmation"):
            status = "proposed"
        elif result.get("ticket_cancelled"):
            status = "rejected"
        elif result.get("quote_id") is not None:
            status = "saved"
        else:
            return None
        if result.get("total") is None:
            return None
        labor = "Diagnóstico técnico" if result.get("labor_task_type") == "diagnosis" else "Mano de obra"
        lines = [QuoteLine(label=labor, amount=result.get("labor_cost", 0))]
        lines += [
            QuoteLine(
                label=f"{part['name']} × {part['quantity']}",
                amount=part["unit_price"] * int(part["quantity"]),
            )
            for part in result.get("available_parts", [])
        ]
        return Quote(status=status, lines=lines, total=result["total"])

    @staticmethod
    def ticket(result: dict[str, Any]) -> TicketRef | None:
        code = result.get("ticket_code")
        if result.get("quote_id") is None or not isinstance(code, str) or not code:
            return None
        return TicketRef(code=code, status=result.get("ticket_status", "QUOTED"))
