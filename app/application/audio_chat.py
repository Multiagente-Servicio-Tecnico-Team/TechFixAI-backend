"""Caso de uso: transcribe una entrada y la entrega al chat compartido."""
from dataclasses import dataclass
from collections.abc import Callable
from typing import Any, Literal
from uuid import UUID

from app.application.audio_requests import AudioRequestLease, AudioRequestRegistry
from app.application.chat import ChatTurn, SendChatMessage
from app.application.errors import (
    AudioRequestError,
    AudioTooLarge,
    AudioTranscriptionTimeout,
    AudioUnavailable,
    UnsupportedAudioType,
)
from app.application.ports import AudioTranscriber

SUPPORTED_AUDIO_TYPES = frozenset({
    "audio/flac", "audio/mpeg", "audio/mp4", "audio/mpga", "audio/ogg",
    "audio/wav", "audio/webm", "audio/x-wav", "video/mp4",
})


@dataclass(frozen=True)
class AudioChatResult:
    transcript: str
    turn: Any


class SendAudioChatMessage:
    def __init__(self, transcriber: AudioTranscriber, send_message: SendChatMessage,
                 registry: AudioRequestRegistry, *, max_bytes: int = 25_000_000,
                 max_duration_ms: int = 120_000):
        self._transcriber = transcriber
        self._send_message = send_message
        self._registry = registry
        self._max_bytes = max_bytes
        self._max_duration_ms = max_duration_ms

    def execute(self, *, customer_id: int, audio: bytes, content_type: str, duration_ms: int,
                pattern: Literal["hierarchical", "orchestrator", "decentralized"],
                request_id: str, conversation_id: str | None = None,
                principal_role: Literal["CUSTOMER", "ADMIN"] = "CUSTOMER",
                message_handler: Callable[[str], Any] | None = None) -> AudioChatResult:
        try:
            UUID(request_id)
        except (ValueError, TypeError, AttributeError) as exc:
            raise AudioRequestError() from exc
        if not 1 <= duration_ms <= self._max_duration_ms:
            raise AudioRequestError()
        if content_type.lower().split(";", 1)[0].strip() not in SUPPORTED_AUDIO_TYPES:
            raise UnsupportedAudioType()
        if not audio:
            raise AudioRequestError()
        if len(audio) > self._max_bytes:
            raise AudioTooLarge()

        fingerprint = self._registry.fingerprint(
            audio, duration_ms=duration_ms, pattern=pattern, conversation_id=conversation_id,
            role=principal_role,
        )
        lease = self._registry.begin(customer_id, request_id, fingerprint, role=principal_role)
        if lease.cached is not None:
            return lease.cached
        try:
            transcription = self._transcriber.transcribe(audio, content_type=content_type)
            text = " ".join(transcription.text.split())
            if not text or len(text) > 2000:
                raise AudioRequestError()
            if message_handler is not None:
                turn = message_handler(text)
            elif principal_role == "CUSTOMER":
                turn = self._send_message.execute(
                    customer_id=customer_id, pattern=pattern, message=text,
                    conversation_id=conversation_id,
                )
            else:
                raise AudioRequestError()
            result = AudioChatResult(text, turn)
            self._registry.complete(lease, result)
            return result
        except TimeoutError as exc:
            self._registry.release(lease)
            raise AudioTranscriptionTimeout() from exc
        except AudioUnavailable:
            self._registry.release(lease)
            raise
        except Exception:
            self._registry.release(lease)
            raise
