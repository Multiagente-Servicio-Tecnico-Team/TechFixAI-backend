from contextlib import nullcontext
from decimal import Decimal
from types import SimpleNamespace

from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from app.accounts.config import Settings as AccountSettings
from app.accounts.session import SessionCustomer, SessionError
from app.adapters.patterns.registry import PATTERN_NAMES
from app.application.ports import TranscriptionResult
from app.domain.chat import PatternReply
from app.infrastructure.chat_app import build_chat_app
from tests.integration.customer_fakes import customer_profiles_factory
from app.settings import Settings


class Graph:
    def __init__(self, name): self.id, self.calls = name, []
    def get_state(self, config): return SimpleNamespace(values={})
    def invoke(self, state, *, config):
        message = state["messages"][-1].content
        self.calls.append((config["configurable"]["thread_id"], state.get("customer_id", state.get("user_id")), message))
        return {"messages": [AIMessage(content=f"recibido: {message}")]}


class Transcriber:
    def __init__(self): self.calls = []
    def transcribe(self, audio, *, content_type):
        self.calls.append((audio, content_type))
        return TranscriptionResult("consulta desde voz")


def make_client(enabled=True, transcriber=None, max_bytes=25_000_000):
    account_settings = AccountSettings(database_url=None, auth_secret="s" * 48, secure_cookie=False)
    class Guard:
        settings = account_settings
        def require_customer(self, request):
            if request.cookies.get("test-session") != "ok":
                raise SessionError(401, "Inicia sesión para continuar.", "session_required")
            return SessionCustomer(9, "Test", None, "test@example.test", "CUSTOMER")
    settings = Settings(
        groq_api_key=None, groq_model=None, database_url=None, langsmith_api_key=None,
        langsmith_tracing=False, langsmith_project="test", langsmith_hide_inputs=True,
        langsmith_hide_outputs=True, labor_maintenance_price=Decimal("35"),
        labor_diagnosis_price=Decimal("50"), audio_transcription_enabled=enabled,
        audio_max_bytes=max_bytes,
    )
    graphs = {key: Graph(key) for key in PATTERN_NAMES}
    transcriber = transcriber or Transcriber()
    app = build_chat_app(
        session_guard=Guard(),
        graph_factories={name: (lambda graph=graph: graph) for name, graph in graphs.items()},
        settings_factory=lambda: settings,
        trace_context_factory=nullcontext,
        audio_transcriber=transcriber,
        customer_repository_factory=customer_profiles_factory(),
    )
    client = TestClient(app)
    client.cookies.set("test-session", "ok")
    return client, graphs, transcriber


def audio_data(request_id="00000000-0000-0000-0000-000000000001", **extra):
    return {
        "duration_ms": "5000", "pattern": "hierarchical", "request_id": request_id,
        **extra,
    }


def test_audio_route_requires_session_and_transcribes_into_selected_pattern():
    client, graphs, transcriber = make_client()
    client.cookies.clear()
    denied = client.post("/api/chat/audio", data=audio_data(), files={"audio": ("voice.webm", b"audio", "audio/webm")})
    assert denied.status_code == 401
    client.cookies.set("test-session", "ok")
    response = client.post("/api/chat/audio", data=audio_data(pattern="decentralized"), files={"audio": ("voice.webm", b"audio", "audio/webm")})
    assert response.status_code == 200, response.text
    assert response.json()["transcript"] == "consulta desde voz"
    assert response.json()["reply"] == "recibido: consulta desde voz"
    # El patrón recibe el cliente comercial del perfil de la sesión (usuario 9 -> perfil 1009), no el id de la cuenta.
    assert graphs["decentralized"].calls[0][1:] == (1009, "consulta desde voz")
    assert not graphs["hierarchical"].calls and not graphs["orchestrator"].calls
    assert len(transcriber.calls) == 1


def test_audio_then_text_continue_same_conversation_and_idempotent_retry():
    client, graphs, transcriber = make_client()
    first = client.post("/api/chat/audio", data=audio_data(), files={"audio": ("voice.webm", b"audio", "audio/webm")})
    conversation_id = first.json()["conversation_id"]
    retry = client.post("/api/chat/audio", data=audio_data(), files={"audio": ("voice.webm", b"audio", "audio/webm")})
    conflict = client.post(
        "/api/chat/audio", data=audio_data(), files={"audio": ("voice.webm", b"different audio", "audio/webm")}
    )
    text = client.post("/api/chat", json={
        "conversation_id": conversation_id, "message": "sigo por escrito", "pattern": "hierarchical",
    })
    assert retry.status_code == 200 and retry.json() == first.json()
    assert conflict.status_code == 409
    assert text.status_code == 200 and text.json()["conversation_id"] == conversation_id
    assert [call[2] for call in graphs["hierarchical"].calls] == ["consulta desde voz", "sigo por escrito"]
    assert len(transcriber.calls) == 1


def test_audio_disabled_is_recoverable_and_does_not_run_provider_or_pattern():
    client, graphs, transcriber = make_client(enabled=False)
    response = client.post("/api/chat/audio", data=audio_data(), files={"audio": ("voice.webm", b"audio", "audio/webm")})
    assert response.status_code == 503
    assert not transcriber.calls and not graphs["hierarchical"].calls


def test_audio_invalid_type_empty_transcript_and_provider_errors_do_not_start_a_turn():
    client, graphs, transcriber = make_client()
    invalid_type = client.post("/api/chat/audio", data=audio_data(), files={"audio": ("voice.bin", b"audio", "application/octet-stream")})
    assert invalid_type.status_code == 415
    assert not transcriber.calls

    class BlankTranscriber:
        def transcribe(self, audio, *, content_type): return TranscriptionResult("  ")
    blank_client, blank_graphs, _ = make_client(transcriber=BlankTranscriber())
    blank = blank_client.post("/api/chat/audio", data=audio_data(), files={"audio": ("voice.webm", b"audio", "audio/webm")})
    assert blank.status_code == 422
    assert not blank_graphs["hierarchical"].calls

    class LongTranscriber:
        def transcribe(self, audio, *, content_type): return TranscriptionResult("x" * 2001)
    long_client, long_graphs, _ = make_client(transcriber=LongTranscriber())
    too_long = long_client.post("/api/chat/audio", data=audio_data(), files={"audio": ("voice.webm", b"audio", "audio/webm")})
    assert too_long.status_code == 422
    assert not long_graphs["hierarchical"].calls

    class FailedTranscriber:
        def transcribe(self, audio, *, content_type):
            from app.application.errors import AudioUnavailable
            raise AudioUnavailable()
    failed_client, failed_graphs, _ = make_client(transcriber=FailedTranscriber())
    failed = failed_client.post("/api/chat/audio", data=audio_data(), files={"audio": ("voice.webm", b"audio", "audio/webm")})
    assert failed.status_code == 503
    assert not failed_graphs["hierarchical"].calls

    class SlowTranscriber:
        def transcribe(self, audio, *, content_type):
            from app.application.errors import AudioTranscriptionTimeout
            raise AudioTranscriptionTimeout()
    timeout_client, timeout_graphs, _ = make_client(transcriber=SlowTranscriber())
    timeout = timeout_client.post("/api/chat/audio", data=audio_data(), files={"audio": ("voice.webm", b"audio", "audio/webm")})
    assert timeout.status_code == 504
    assert not timeout_graphs["hierarchical"].calls


def test_audio_size_and_duration_limits_fail_before_provider():
    client, graphs, transcriber = make_client(max_bytes=4)
    oversized = client.post("/api/chat/audio", data=audio_data(), files={"audio": ("voice.webm", b"12345", "audio/webm")})
    assert oversized.status_code == 413
    too_long = client.post(
        "/api/chat/audio", data={**audio_data(), "duration_ms": "120001"},
        files={"audio": ("voice.webm", b"1234", "audio/webm")},
    )
    assert too_long.status_code == 422
    assert not transcriber.calls and not graphs["hierarchical"].calls


def test_incremental_body_cap_rejects_excess_multipart_payload():
    client, graphs, transcriber = make_client(max_bytes=4)
    response = client.post(
        "/api/chat/audio", data=audio_data(),
        files={"audio": ("voice.webm", b"x" * 100_000, "audio/webm")},
    )
    assert response.status_code == 413
    assert not transcriber.calls and not graphs["hierarchical"].calls


def test_audio_quota_is_checked_before_the_sixth_transcription():
    client, graphs, transcriber = make_client()
    for index in range(5):
        response = client.post(
            "/api/chat/audio",
            data=audio_data(request_id=f"00000000-0000-0000-0000-{index + 1:012d}"),
            files={"audio": ("voice.webm", b"audio" + bytes([index]), "audio/webm")},
        )
        assert response.status_code == 200
    limited = client.post(
        "/api/chat/audio",
        data=audio_data(request_id="00000000-0000-0000-0000-000000000006"),
        files={"audio": ("voice.webm", b"another", "audio/webm")},
    )
    assert limited.status_code == 429
    assert len(transcriber.calls) == 5
