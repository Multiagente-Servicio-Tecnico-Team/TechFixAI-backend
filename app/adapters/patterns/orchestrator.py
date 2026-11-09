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

    def prepare(self, graph: Any, state: dict[str, Any], config: dict[str, Any]) -> None:
        previous = graph.get_state(config).values
        state["turn_start_index"] = len(previous.get("messages", []))
        if (not previous.get("awaiting_sales_quote_confirmation")
                and not previous.get("direct_sale_pending")):
            state.update(sales_quote_id=None, sales_quote_status=None,
                         sales_quote_kind=None, direct_sale_pending=False,
                         direct_sale_product="", direct_sale_quantity=None,
                         direct_sale_candidates=[],
                         sales_payment_code=None, pc_build_selected=False,
                         selected_build_profile_id=None, selected_build_profile_name=None,
                         build_total=None, build_labor_cost=None, matched_parts=[])

    def to_reply(self, result: dict[str, Any]) -> PatternReply:
        response = result.get("response")
        text = response if isinstance(response, str) and response.strip() else last_message_text(result)
        return PatternReply(
            reply=text,
            quote=self.quote(result),
            ticket=self.ticket(result),
            pending_quote=bool(result.get("awaiting_ticket_confirmation")
                                or result.get("awaiting_sales_quote_confirmation")),
            quote_id=result.get("sales_quote_id") or result.get("quote_id"),
        )

    @staticmethod
    def quote(result: dict[str, Any]) -> Quote | None:
        sales_status = result.get("sales_quote_status")
        if (result.get("sales_quote_id") is not None
                and sales_status in {"PENDING", "ACCEPTED", "REJECTED", "CANCELLED", "EXPIRED"}):
            status = "proposed" if sales_status == "PENDING" else (
                "confirmed" if sales_status == "ACCEPTED" else "rejected"
            )
            parts = result.get("matched_parts", [])
            lines = ([QuoteLine(label="Ensamble", amount=result.get("build_labor_cost", 0))]
                     if result.get("sales_quote_kind", "PC_BUILD") == "PC_BUILD" else [])
            lines.extend(QuoteLine(
                label=f"{part['name']} × {part['quantity']}",
                amount=part.get("subtotal", part["unit_price"] * int(part["quantity"])),
            ) for part in parts)
            total = result.get("build_total")
            return Quote(status=status, lines=lines, total=total) if total is not None else None
        if result.get("awaiting_ticket_confirmation"):
            status = "proposed"
        elif result.get("ticket_cancelled"):
            status = "rejected"
        elif result.get("quote_id") is not None:
            status = (
                "confirmed"
                if result.get("ticket_status") == "PAYMENT_PENDING"
                else "saved"
            )
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
        if not isinstance(code, str) or not code:
            return None
        return TicketRef(code=code, status=result.get("ticket_status", "NEW"))
