"""Rutas HTTP del chat: traducen JSON ↔ casos de uso y errores ↔ códigos HTTP."""
from collections.abc import Callable, Mapping
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel, ConfigDict, Field
from fastapi.responses import JSONResponse

from app.accounts.session import SessionCustomer
from app.application.chat import SendChatMessage
from app.application.audio_chat import SendAudioChatMessage
from app.application.errors import (
    AudioIdempotencyConflict, AudioQuotaExceeded, AudioRequestError,
    AudioTranscriptionTimeout, AudioUnavailable,
    PatternFailure, RateLimited, StorageUnavailable,
)
from app.application.tickets import ListCustomerTickets
from app.chat.contract import AudioChatOut, ChatIn, ChatOut, QuoteLine, QuoteOut, TicketOut
from app.domain.chat import PatternReply
from app.domain.errors import ConversationNotFound, DomainError
from app.domain.money import money_text
from app.domain.tickets import CustomerTicket


class PortalTicketCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=2, max_length=200)
    failure_description: str = Field(min_length=5, max_length=10000)
    request_type: str = Field(pattern="^(REPAIR|SUPPORT|PC_BUILD|WARRANTY_CLAIM)$")


def create_chat_router(
    *,
    send_message: SendChatMessage,
    list_tickets: ListCustomerTickets,
    require_customer: Callable[[Request], SessionCustomer],
    pattern_names: Mapping[str, str],
    audio_message: SendAudioChatMessage | None = None,
    audio_enabled: bool = False,
    audio_max_bytes: int = 25_000_000,
    create_portal_ticket: Callable[..., dict[str, Any]] | None = None,
) -> APIRouter:
    router = APIRouter()

    @router.get("/api/chat/patterns")
    def patterns(_customer: SessionCustomer = Depends(require_customer)):
        return {"patterns": [{"id": key, "name": name} for key, name in pattern_names.items()]}

    @router.get("/api/customer/tickets")
    def customer_tickets(customer: SessionCustomer = Depends(require_customer)):
        customer_id = customer.commercial_customer_id or customer.id
        try:
            tickets = list_tickets.execute(customer_id)
        except StorageUnavailable as exc:
            raise HTTPException(status_code=503, detail=exc.detail) from exc
        return {"tickets": [ticket_json(ticket) for ticket in tickets]}

    @router.post("/api/customer/tickets", status_code=201)
    def create_customer_ticket(body: PortalTicketCreate, customer: SessionCustomer = Depends(require_customer)):
        if create_portal_ticket is None:
            raise HTTPException(status_code=503, detail="La creación de tickets no está disponible.")
        try:
            return create_portal_ticket(
                customer_id=customer.commercial_customer_id or customer.id,
                title=body.title.strip(),
                failure_description=body.failure_description.strip(),
                request_type=body.request_type,
            )
        except LookupError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except (OSError, RuntimeError) as exc:
            raise HTTPException(status_code=503, detail="No se pudo registrar el ticket.") from exc

    @router.post("/api/chat", response_model=ChatOut, response_model_exclude_none=True)
    def chat(body: ChatIn, customer: SessionCustomer = Depends(require_customer)):
        try:
            turn = send_message.execute(
                customer_id=customer.commercial_customer_id or customer.id,
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

    @router.post(
        "/api/chat/audio",
        response_model=AudioChatOut,
        response_model_exclude_none=True,
        responses={
            401: {"description": "Sesión requerida"}, 403: {"description": "Solo clientes"},
            409: {"description": "Conversación o clave idempotente en conflicto"},
            413: {"description": "Carga o archivo demasiado grande"},
            415: {"description": "Formato no admitido"}, 422: {"description": "Audio inválido o sin voz"},
            429: {"description": "Cuota agotada"}, 503: {"description": "Transcripción no disponible"},
            502: {"description": "El patrón de chat no completó el turno"},
            504: {"description": "Timeout del proveedor"},
        },
    )
    def audio_chat(
        audio: UploadFile = File(...),
        duration_ms: int = Form(..., ge=1, le=120_000),
        pattern: str = Form(..., pattern="^(hierarchical|orchestrator|decentralized)$"),
        request_id: str = Form(...),
        conversation_id: UUID | None = Form(default=None),
        customer: SessionCustomer = Depends(require_customer),
    ):
        if not audio_enabled or audio_message is None:
            return JSONResponse(status_code=503, content={
                "detail": "La transcripción de audio no está disponible. Puedes continuar por escrito.",
                "code": "audio_unavailable",
            })
        try:
            content_type = audio.content_type or ""
            content = audio.file.read(audio_max_bytes + 1)
            result = audio_message.execute(
                customer_id=customer.commercial_customer_id or customer.id,
                audio=content,
                content_type=content_type,
                duration_ms=duration_ms,
                pattern=pattern,
                request_id=request_id,
                conversation_id=str(conversation_id) if conversation_id else None,
            )
        except AudioQuotaExceeded as exc:
            return JSONResponse(
                status_code=exc.status_code,
                content={"detail": exc.detail, "code": exc.code},
                headers={"Retry-After": "60"},
            )
        except (AudioRequestError, AudioIdempotencyConflict) as exc:
            return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail, "code": exc.code})
        except RateLimited as exc:
            return JSONResponse(status_code=429, content={"detail": exc.detail, "code": "rate_limited"})
        except DomainError as exc:
            status = 404 if isinstance(exc, ConversationNotFound) else 409
            return JSONResponse(status_code=status, content={"detail": exc.detail, "code": exc.code})
        except StorageUnavailable as exc:
            raise HTTPException(status_code=503, detail=exc.detail) from exc
        except PatternFailure as exc:
            raise HTTPException(status_code=502, detail=exc.detail) from exc
        except (AudioUnavailable, AudioTranscriptionTimeout) as exc:
            return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail, "code": exc.code})
        finally:
            audio.file.close()
        output = chat_out(result.turn.conversation_id, result.turn.pattern, result.turn.reply)
        return AudioChatOut(**output.model_dump(), transcript=result.transcript)

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
        quote_id=reply.quote_id,
        ticket=TicketOut(code=reply.ticket.code, status=reply.ticket.status) if reply.ticket else None,
    )


def _date(value: Any) -> Any:
    return value.isoformat() if hasattr(value, "isoformat") else value


def _money(value: Any) -> str | None:
    return None if value is None else money_text(value)


def ticket_json(ticket: CustomerTicket) -> dict[str, Any]:
    quote = ticket.quote
    quotes = ticket.quotes or ((quote,) if quote else ())
    def quote_json(item):
        return {
            "status": item.status,
            "labor_cost": _money(item.labor_cost),
            "parts_cost": _money(item.parts_cost),
            "total_amount": _money(item.total_amount),
            "created_at": _date(item.created_at),
            "lines": [
                {"name": line.name, "quantity": line.quantity,
                 "unit_price": _money(line.unit_price), "subtotal": _money(line.subtotal)}
                for line in item.lines
            ],
        }
    return {
        "id": ticket.id,
        "code": ticket.code,
        "customer_id": ticket.customer_id,
        "title": ticket.title,
        "failure_description": ticket.failure_description,
        "request_type": ticket.request_type,
        "diagnosis_type": ticket.diagnosis_type,
        "hardware_diagnosis": ticket.hardware_diagnosis,
        "software_diagnosis": ticket.software_diagnosis,
        "status": ticket.status,
        "created_at": _date(ticket.created_at),
        "updated_at": _date(ticket.updated_at),
        "quotes": [quote_json(item) for item in quotes],
        "quote": (
            quote_json(quote)
            if quote
            else None
        ),
    }
