"""Adaptador Groq Speech-to-Text; los errores del proveedor no filtran su texto."""
from typing import Any

from groq import APIError, APITimeoutError, APIConnectionError, APIStatusError, Groq

from app.application.errors import AudioTranscriptionTimeout, AudioUnavailable, AudioRequestError
from app.application.ports import TranscriptionResult

SAFE_EXTENSIONS = {
    "audio/flac": ".flac", "audio/mpeg": ".mp3", "audio/mp4": ".m4a",
    "audio/mpga": ".mpga", "audio/ogg": ".ogg", "audio/wav": ".wav",
    "audio/x-wav": ".wav", "audio/webm": ".webm", "video/mp4": ".mp4",
}


class GroqAudioTranscriber:
    def __init__(self, api_key: str, *, timeout: float = 30.0, client: Any | None = None):
        self._client = client or Groq(api_key=api_key, timeout=timeout)

    def transcribe(self, audio: bytes, *, content_type: str) -> TranscriptionResult:
        try:
            normalized_type = content_type.lower().split(";", 1)[0].strip()
            result = self._client.audio.transcriptions.create(
                file=(f"recording{SAFE_EXTENSIONS.get(normalized_type, '')}", audio, normalized_type),
                model="whisper-large-v3-turbo",
                language="es",
                response_format="verbose_json",
                temperature=0,
            )
        except APITimeoutError as exc:
            raise AudioTranscriptionTimeout() from exc
        except (APIConnectionError, APIStatusError) as exc:
            raise AudioUnavailable() from exc
        except APIError as exc:
            raise AudioUnavailable() from exc
        segments = getattr(result, "segments", None) or []
        if not segments:
            raise AudioRequestError()
        try:
            if all(_value(segment, "no_speech_prob", 0) >= 0.6 for segment in segments):
                raise AudioRequestError()
        except TypeError as exc:
            raise AudioRequestError() from exc
        text = getattr(result, "text", None)
        if not isinstance(text, str):
            raise AudioRequestError()
        return TranscriptionResult(text)


def _value(segment: Any, name: str, default: Any) -> Any:
    return segment.get(name, default) if isinstance(segment, dict) else getattr(segment, name, default)
