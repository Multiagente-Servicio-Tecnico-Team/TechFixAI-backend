from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.adapters.speech.groq import GroqAudioTranscriber
from app.application.errors import AudioRequestError


def client_with_result(result):
    client = SimpleNamespace(audio=SimpleNamespace(transcriptions=SimpleNamespace(create=Mock(return_value=result))))
    return client


def test_groq_transcriber_uses_required_model_and_rejects_silence():
    client = client_with_result(SimpleNamespace(text="hola", segments=[{"no_speech_prob": 0.7}]))
    transcriber = GroqAudioTranscriber("test-key", client=client)
    with pytest.raises(AudioRequestError):
        transcriber.transcribe(b"bytes", content_type="audio/webm")
    kwargs = client.audio.transcriptions.create.call_args.kwargs
    assert kwargs["file"][0] == "recording.webm"
    assert kwargs["model"] == "whisper-large-v3-turbo"
    assert kwargs["language"] == "es" and kwargs["response_format"] == "verbose_json"
    assert kwargs["temperature"] == 0


def test_groq_transcriber_returns_text_when_segment_contains_speech():
    client = client_with_result(SimpleNamespace(text=" hola ", segments=[{"no_speech_prob": 0.1}]))
    result = GroqAudioTranscriber("test-key", client=client).transcribe(b"bytes", content_type="audio/webm")
    assert result.text == " hola "


def test_groq_transcriber_rejects_missing_segments():
    client = client_with_result(SimpleNamespace(text="hola", segments=[]))
    with pytest.raises(AudioRequestError):
        GroqAudioTranscriber("test-key", client=client).transcribe(b"bytes", content_type="audio/webm")
