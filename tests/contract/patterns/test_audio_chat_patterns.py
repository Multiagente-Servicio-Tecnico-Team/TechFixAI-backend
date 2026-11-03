from app.application.audio_chat import SendAudioChatMessage
from app.application.audio_requests import AudioRequestRegistry
from app.application.chat import SendChatMessage
from app.application.conversations import ConversationRegistry
from app.domain.chat import PatternReply
from app.application.ports import TranscriptionResult


class Pattern:
    supports_quotes = False
    def __init__(self, pattern_id): self.id, self.inputs = pattern_id, []
    def reply(self, conversation_id, customer_id, message):
        self.inputs.append(message)
        return PatternReply(reply="respuesta")


class FakeTranscriber:
    def transcribe(self, audio, *, content_type): return TranscriptionResult("  consulta   común ")


class Limiter:
    def blocked(self, key): return False
    def fail(self, key): pass


def test_each_pattern_receives_identical_normalized_audio_transcript():
    patterns = {name: Pattern(name) for name in ("hierarchical", "orchestrator", "decentralized")}
    use_case = SendAudioChatMessage(FakeTranscriber(), SendChatMessage(patterns, ConversationRegistry(), Limiter()), AudioRequestRegistry())
    for index, pattern in enumerate(patterns, 1):
        use_case.execute(
            customer_id=12, audio=b"same audio", content_type="audio/webm", duration_ms=3000,
            pattern=pattern, request_id=f"00000000-0000-0000-0000-{index:012d}",
        )
    assert {tuple(pattern.inputs) for pattern in patterns.values()} == {("consulta común",)}
