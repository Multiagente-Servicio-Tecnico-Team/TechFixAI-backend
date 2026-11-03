"""Adaptador del patrón Jerárquico (`app/agents/jerarquico`)."""
from typing import Any

from langchain_core.messages import HumanMessage

from app.adapters.patterns.base import GraphPattern, last_message_text
from app.domain.chat import PatternReply, Quote, QuoteLine, TicketRef

QUOTE_STATUS_BY_OUTCOME = {"awaiting_confirmation": "proposed", "declined": "rejected"}
TICKET_OUTCOMES = {"quoted", "warranty_claim_registered"}
LABOR_LABELS = {"diagnosis": "Diagnóstico técnico", "pc_build": "Ensamble"}


class HierarchicalPattern(GraphPattern):
    id = "hierarchical"
    name = "Jerárquico"

    def build_graph(self) -> Any:
        from app.agents.jerarquico.graph.builder import build_multiagent_graph

        settings = self._settings_factory()
        settings.require_chat_configuration()
        return build_multiagent_graph(settings=settings)

    def initial_state(self, customer_id: int, message: HumanMessage) -> dict[str, Any]:
        return {"messages": [message], "customer_id": customer_id}

    def to_reply(self, result: dict[str, Any]) -> PatternReply:
        return PatternReply(
            reply=last_message_text(result),
            quote=self.quote(result),
            ticket=self.ticket(result),
            pending_quote=result.get("outcome") == "awaiting_confirmation",
        )

    @staticmethod
    def quote(result: dict[str, Any]) -> Quote | None:
        outcome = result.get("outcome")
        if outcome == "quoted":
            status = "confirmed" if result.get("ticket_status") == "PAYMENT_PENDING" else "saved"
        else:
            status = QUOTE_STATUS_BY_OUTCOME.get(outcome)
        quote = result.get("quote")
        if not quote or not status or quote.get("total_amount") is None:
            return None
        if quote.get("quote_type", result.get("quote_type")) == "DIRECT_SALE":
            labor = "Mano de obra (venta directa)"
        else:
            labor = LABOR_LABELS.get(quote.get("labor_task_type", "maintenance"), "Mano de obra")
        lines = [QuoteLine(label=labor, amount=quote["labor_cost"])]
        lines += [
            QuoteLine(label=f"{part['name']} × {part['quantity']}", amount=part["subtotal"])
            for part in quote.get("parts", [])
        ]
        return Quote(status=status, lines=lines, total=quote["total_amount"])

    @staticmethod
    def ticket(result: dict[str, Any]) -> TicketRef | None:
        code = result.get("ticket_code")
        if result.get("outcome") not in TICKET_OUTCOMES or not isinstance(code, str) or not code:
            return None
        return TicketRef(code=code, status=result.get("ticket_status", "QUOTED"))
