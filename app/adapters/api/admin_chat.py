"""Text and audio routes for the authenticated ADMIN chat."""
from collections.abc import Callable, Mapping
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import SQLAlchemyError

from app.accounts.session import SessionCustomer
from app.infrastructure.admin_chat import AdminChatService
from app.application.capabilities import CapabilityError
from app.application.errors import (
    ApplicationError, AudioIdempotencyConflict, AudioQuotaExceeded, AudioRequestError,
    AudioTranscriptionTimeout, AudioUnavailable, PatternFailure, RateLimited,
    StorageUnavailable, UnsupportedAudioType,
)
from app.application.audio_chat import SendAudioChatMessage
from app.domain.principal import Principal


class AdminChatIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pattern: Literal["hierarchical", "orchestrator", "decentralized"]
    message: str | None = Field(default=None, max_length=4000)
    conversation_id: UUID | None = None
    action: Literal["confirm", "cancel"] | None = None
    proposal_id: UUID | None = None


class AdminProposalOut(BaseModel):
    proposal_id: UUID
    status: str
    summary: str
    resource_type: str
    expires_at: str
    values: dict[str, Any] | None = None
    presentation: dict[str, Any] | None = None


class AdminChatOut(BaseModel):
    conversation_id: UUID
    pattern: Literal["hierarchical", "orchestrator", "decentralized"]
    reply: str
    proposal: AdminProposalOut | None = None
    result: dict[str, Any] | None = None
    presentation: dict[str, Any] | None = None


class AdminAudioChatOut(AdminChatOut):
    transcript: str


def create_admin_chat_router(*, chat_service: AdminChatService,
                             require_admin: Callable[[Request], SessionCustomer],
                             pattern_names: Mapping[str, str],
                             audio_message: SendAudioChatMessage | None = None,
                             audio_enabled: bool = False,
                             audio_max_bytes: int = 25_000_000) -> APIRouter:
    router = APIRouter(tags=["admin chat"])

    def response(turn) -> AdminChatOut:
        return AdminChatOut(
            conversation_id=UUID(turn.conversation_id), pattern=turn.pattern, reply=turn.reply,
            proposal=AdminProposalOut(**turn.proposal) if turn.proposal else None,
            result=turn.result, presentation=turn.presentation,
        )

    def map_error(exc: Exception):
        if isinstance(exc, CapabilityError):
            return JSONResponse(status_code=exc.status, content={"detail": exc.detail, "code": exc.code})
        if isinstance(exc, RateLimited):
            return JSONResponse(status_code=429, content={"detail": exc.detail, "code": exc.code})
        if isinstance(exc, (AudioRequestError, UnsupportedAudioType, AudioUnavailable,
                            AudioTranscriptionTimeout, AudioQuotaExceeded, AudioIdempotencyConflict)):
            return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail, "code": exc.code})
        if isinstance(exc, PatternFailure):
            return JSONResponse(status_code=502, content={"detail": exc.detail, "code": "pattern_failure"})
        if isinstance(exc, (SQLAlchemyError, StorageUnavailable)):
            return JSONResponse(status_code=503, content={"detail": "El servicio administrativo no está disponible.",
                                                           "code": "admin_chat_unavailable"})
        if isinstance(exc, ApplicationError):
            return JSONResponse(status_code=getattr(exc, "status_code", 422),
                                content={"detail": getattr(exc, "detail", str(exc)),
                                         "code": getattr(exc, "code", "application_error")})
        if isinstance(exc, LookupError):
            return JSONResponse(status_code=404, content={"detail": str(exc), "code": "not_found"})
        if isinstance(exc, ValueError):
            return JSONResponse(status_code=422, content={"detail": str(exc), "code": "invalid_operation"})
        raise exc

    @router.get("/api/admin/chat/patterns")
    def patterns(_admin: SessionCustomer = Depends(require_admin)):
        return {"patterns": [{"id": key, "name": name} for key, name in pattern_names.items()]}

    @router.post("/api/admin/chat", response_model=AdminChatOut)
    def chat(body: AdminChatIn, admin: SessionCustomer = Depends(require_admin)):
        try:
            turn = chat_service.execute(
                principal=Principal.from_session(admin), pattern=body.pattern, message=body.message,
                action=body.action, proposal_id=str(body.proposal_id) if body.proposal_id else None,
                conversation_id=str(body.conversation_id) if body.conversation_id else None,
            )
            return response(turn)
        except Exception as exc:
            return map_error(exc)

    @router.post("/api/admin/chat/audio", response_model=AdminAudioChatOut)
    def audio_chat(
        audio: UploadFile = File(...),
        duration_ms: int = Form(..., ge=1, le=120_000),
        pattern: Literal["hierarchical", "orchestrator", "decentralized"] = Form(...),
        request_id: UUID = Form(...),
        conversation_id: UUID | None = Form(default=None),
        action: Literal["confirm", "cancel"] | None = Form(default=None),
        proposal_id: UUID | None = Form(default=None),
        admin: SessionCustomer = Depends(require_admin),
    ):
        if not audio_enabled or audio_message is None:
            return JSONResponse(status_code=503, content={
                "detail": "La transcripción de audio no está disponible. Puedes continuar por escrito.",
                "code": "audio_unavailable",
            })
        try:
            principal = Principal.from_session(admin)
            content = audio.file.read(audio_max_bytes + 1)
            result = audio_message.execute(
                customer_id=principal.actor_id, principal_role="ADMIN", audio=content,
                content_type=audio.content_type or "", duration_ms=duration_ms, pattern=pattern,
                request_id=str(request_id), conversation_id=str(conversation_id) if conversation_id else None,
                message_handler=lambda transcript: chat_service.execute(
                    principal=principal, pattern=pattern, message=transcript, action=action,
                    proposal_id=str(proposal_id) if proposal_id else None,
                    conversation_id=str(conversation_id) if conversation_id else None,
                ),
            )
            turn = result.turn
            return AdminAudioChatOut(
                conversation_id=UUID(turn.conversation_id), pattern=turn.pattern, reply=turn.reply,
                proposal=AdminProposalOut(**turn.proposal) if turn.proposal else None,
                result=turn.result, presentation=turn.presentation, transcript=result.transcript,
            )
        except Exception as exc:
            return map_error(exc)
        finally:
            audio.file.close()

    return router
