from app.application.audio_chat import SendAudioChatMessage
from app.application.audio_requests import AudioRequestRegistry
from app.application.chat import SendChatMessage
from app.application.conversations import ConversationRegistry
from app.application.errors import AudioRequestError
from app.domain.chat import PatternReply


class Pattern:
    supports_quotes = False
    def __init__(self, name): self.id, self.calls = name, []
    def reply(self, conversation_id, customer_id, message):
        self.calls.append((conversation_id, customer_id, message))
        return PatternReply(reply="ok")


class Limiter:
    def blocked(self, key): return False
    def fail(self, key): pass


class Transcriber:
    def __init__(self): self.calls = 0
    def transcribe(self, audio, *, content_type):
        from app.application.ports import TranscriptionResult
        self.calls += 1
        return TranscriptionResult("  necesito   ayuda  ")


def test_audio_transcription_is_shared_by_all_patterns_and_idempotent():
    patterns = {name: Pattern(name) for name in ("hierarchical", "orchestrator", "decentralized")}
    chat = SendChatMessage(patterns, ConversationRegistry(), Limiter())
    speech = Transcriber()
    use_case = SendAudioChatMessage(speech, chat, AudioRequestRegistry())
    results = [use_case.execute(
        customer_id=8, audio=b"sound", content_type="audio/webm", duration_ms=4000,
        pattern=name, request_id=f"00000000-0000-0000-0000-00000000000{i}",
    ) for i, name in enumerate(patterns, 1)]

    assert [p.calls[0][2] for p in patterns.values()] == ["necesito ayuda"] * 3
    assert [r.transcript for r in results] == ["necesito ayuda"] * 3
    retry = use_case.execute(
        customer_id=8, audio=b"sound", content_type="audio/webm", duration_ms=4000,
        pattern="hierarchical", request_id="00000000-0000-0000-0000-000000000001",
    )
    assert retry == results[0]
    assert speech.calls == 3
    assert len(patterns["hierarchical"].calls) == 1


def test_transcript_over_chat_limit_is_rejected_before_pattern_invocation():
    class LongTranscriber:
        def transcribe(self, audio, *, content_type):
            from app.application.ports import TranscriptionResult
            return TranscriptionResult("x" * 2001)
    pattern = Pattern("hierarchical")
    send = SendChatMessage({pattern.id: pattern}, ConversationRegistry(), Limiter())
    use_case = SendAudioChatMessage(LongTranscriber(), send, AudioRequestRegistry())
    import pytest
    with pytest.raises(AudioRequestError):
        use_case.execute(
            customer_id=1, audio=b"audio", content_type="audio/webm", duration_ms=500,
            pattern="hierarchical", request_id="00000000-0000-0000-0000-000000000001",
        )
    assert not pattern.calls
