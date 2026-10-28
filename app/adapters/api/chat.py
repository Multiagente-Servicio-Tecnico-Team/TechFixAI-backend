"""Rutas HTTP del chat: traducen JSON ↔ casos de uso y errores ↔ códigos HTTP."""
from collections.abc import Callable, Mapping
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from app.accounts.session import SessionCustomer
from app.application.chat import SendChatMessage
from app.application.errors import PatternFailure, RateLimited, StorageUnavailable
from app.application.tickets import ListCustomerTickets
from app.chat.contract import ChatIn, ChatOut, QuoteLine, QuoteOut, TicketOut
from app.domain.chat import PatternReply
from app.domain.errors import ConversationNotFound, DomainError
from app.domain.money import money_text
from app.domain.tickets import CustomerTicket


def create_chat_router(
    *,
    send_message: SendChatMessage,
    list_tickets: ListCustomerTickets,
    require_customer: Callable[[Request], SessionCustomer],
    pattern_names: Mapping[str, str],
) -> APIRouter:
    router = APIRouter()

    @router.get("/api/chat/patterns")
    def patterns(_customer: SessionCustomer = Depends(require_customer)):
        return {"patterns": [{"id": key, "name": name} for key, name in pattern_names.items()]}

    @router.get("/api/customer/tickets")
    def customer_tickets(customer: SessionCustomer = Depends(require_customer)):
        try:
            tickets = list_tickets.execute(customer.id)
        except StorageUnavailable as exc:
            raise HTTPException(status_code=503, detail=exc.detail) from exc
        return {"tickets": [ticket_json(ticket) for ticket in tickets]}

    @router.post("/api/chat", response_model=ChatOut, response_model_exclude_none=True)
    def chat(body: ChatIn, customer: SessionCustomer = Depends(require_customer)):
        try:
            turn = send_message.execute(
                customer_id=customer.id,
                pattern=body.pattern,
                message=body.message,
                action=body.action,
                conversation_id=body.conversation_id,
            )
        except RateLimited as exc:
            return JSONResponse(status_code=429, content={"detail": exc.detail})
        except DomainError as exc:
            status = 404 if isinstance(exc, ConversationNotFound) else 409
            return JSONResponse(status_code=status, content={"detail": exc.detail, "code": exc.code})
        except StorageUnavailable as exc:
            raise HTTPException(status_code=503, detail=exc.detail) from exc
        except PatternFailure as exc:
            raise HTTPException(status_code=502, detail=exc.detail) from exc
        return chat_out(turn.conversation_id, turn.pattern, turn.reply)

    return router


def chat_out(conversation_id: str, pattern: str, reply: PatternReply) -> ChatOut:
    quote = reply.quote
    return ChatOut(
        conversation_id=conversation_id,
        reply=reply.reply,
        pattern=pattern,
        quote=(
            QuoteOut(
                status=quote.status,
                lines=[QuoteLine(label=line.label, amount=money_text(line.amount)) for line in quote.lines],
                total=money_text(quote.total),
                currency=quote.currency,
            )
            if quote
            else None
        ),
        ticket=TicketOut(code=reply.ticket.code, status=reply.ticket.status) if reply.ticket else None,
    )


def _date(value: Any) -> Any:
    return value.isoformat() if hasattr(value, "isoformat") else value


def _money(value: Any) -> str | None:
    return None if value is None else money_text(value)


def ticket_json(ticket: CustomerTicket) -> dict[str, Any]:
    quote = ticket.quote
    return {
        "code": ticket.code,
        "title": ticket.title,
        "failure_description": ticket.failure_description,
        "request_type": ticket.request_type,
        "status": ticket.status,
        "created_at": _date(ticket.created_at),
        "updated_at": _date(ticket.updated_at),
        "quote": (
            {
                "status": quote.status,
                "labor_cost": _money(quote.labor_cost),
                "parts_cost": _money(quote.parts_cost),
                "total_amount": _money(quote.total_amount),
                "created_at": _date(quote.created_at),
                "lines": [
                    {
                        "name": line.name,
                        "quantity": line.quantity,
                        "unit_price": _money(line.unit_price),
                        "subtotal": _money(line.subtotal),
                    }
                    for line in quote.lines
                ],
            }
            if quote
            else None
        ),
    }
