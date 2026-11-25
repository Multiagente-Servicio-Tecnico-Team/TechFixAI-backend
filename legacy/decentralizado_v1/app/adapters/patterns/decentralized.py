"""Adaptador del patrón Red descentralizada (`app/agents/decentralized`)."""
from decimal import Decimal
from typing import Any

from langchain_core.messages import HumanMessage

from app.adapters.patterns.base import GraphPattern, last_message_text
from app.domain.chat import PatternReply, Quote, QuoteLine, TicketRef


class DecentralizedPattern(GraphPattern):
    id = "decentralized"
    name = "Red descentralizada"
    supports_quotes = True

    def build_graph(self) -> Any:
        from langgraph.checkpoint.memory import MemorySaver

        from app.agents.decentralized.graph import build_graph
        from app.database.repository import ServiceRepository
        from app.adapters.persistence.sales_quotes import SalesQuoteRepositoryAdapter

        service_repository = ServiceRepository()
        return build_graph(
            checkpointer=MemorySaver(), ticket_repository=service_repository, ticket_writes=True,
            sales_quote_writes=True, sales_quote_repository=SalesQuoteRepositoryAdapter(),
            service_quote_repository=service_repository,
        )

    def invocation_context(self, *, conversation_id: str, customer_id: int) -> dict[str, Any]:
        return {"authenticated_customer_id": customer_id}

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
        ticket_code = result.get("ticket_code")
        ticket = (
            TicketRef(
                code=ticket_code,
                status=result.get("ticket_status", "NEW"),
            )
            if isinstance(ticket_code, str) and ticket_code
            else None
        )
        quote = None
        raw_quote = result.get("quote")
        quote_id = result.get("quote_id")
        raw_total = (raw_quote.get("total", raw_quote.get("total_amount"))
                     if isinstance(raw_quote, dict) else None)
        if isinstance(raw_quote, dict) and type(raw_total) in {int, float, str, Decimal}:
            quote_status = result.get("quote_status")
            status = ({"PENDING": "proposed", "ACCEPTED": "confirmed", "REJECTED": "rejected",
                       "EXPIRED": "rejected", "CANCELLED": "rejected",
                       "proposed": "proposed", "confirmed": "confirmed", "rejected": "rejected"}.get(quote_status)
                      or {"proposed": "proposed", "confirmed": "confirmed", "rejected": "rejected"}.get(raw_quote.get("status")))
            if status:
                lines = []
                labor = raw_quote.get("labor_total", raw_quote.get("labor_cost"))
                if labor not in {None, "0", "0.00", 0, 0.0}:
                    lines.append(QuoteLine(label="Ensamblaje", amount=labor))
                for part in raw_quote.get("parts", []):
                    amount = part.get("subtotal")
                    if amount is None and part.get("unit_price") is not None:
                        amount = Decimal(str(part["unit_price"])) * int(part["quantity"])
                    if amount is not None:
                        lines.append(QuoteLine(
                            label=f"{part['name']} × {part['quantity']}",
                            amount=amount,
                        ))
                quote = Quote(status=status, lines=tuple(lines), total=raw_total)
        return PatternReply(reply=last_message_text(result), quote=quote, ticket=ticket,
                            pending_quote=(result.get("quote_status") in {"PENDING", "proposed"}
                                           or (isinstance(raw_quote, dict) and raw_quote.get("status") == "proposed")),
                            quote_id=quote_id if type(quote_id) is int else None)
