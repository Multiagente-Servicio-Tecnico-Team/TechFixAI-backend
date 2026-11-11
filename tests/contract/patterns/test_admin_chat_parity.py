from collections import deque
from decimal import Decimal

import pytest

from app.infrastructure.admin_chat import AdminChatService, AdminCommand
from app.application.admin_conversations import AdminConversationRegistry
from app.application.audio_chat import SendAudioChatMessage
from app.application.audio_requests import AudioRequestRegistry
from app.application.capabilities import CapabilityError
from app.application.ports import TranscriptionResult
from app.domain.chat import PatternReply
from app.domain.principal import Principal
from app.settings import Settings


class Limiter:
    def blocked(self, _key):
        return False

    def fail(self, _key):
        pass


class CommandModel:
    def __init__(self, commands):
        self.commands = deque(commands)

    def with_structured_output(self, _schema):
        return self

    def invoke(self, _messages):
        return self.commands.popleft()


class AdminCapabilities:
    def __init__(self):
        self.executed = []
        self.reads = []

    def read(self, action, arguments):
        self.reads.append((action, arguments))
        return {"items": []}

    def prepare(self, action, arguments, *, actor_id):
        values = {**arguments, "prepared_by": actor_id}
        return values, {"values": values, "precondition": {}}

    def execute(self, action, arguments, *, actor_id, idempotency_key, precondition):
        self.executed.append((action, arguments, actor_id, idempotency_key, precondition))
        return {"updated": True}


def _service(commands):
    settings = Settings(
        groq_api_key="test-key", groq_model="test-model",
        database_url="postgresql+pg8000://localhost/test",
        langsmith_api_key=None, langsmith_tracing=False,
        langsmith_project="contract-tests", langsmith_hide_inputs=True,
        langsmith_hide_outputs=True, labor_maintenance_price=Decimal("35.00"),
        labor_diagnosis_price=Decimal("50.00"),
    )
    capabilities = AdminCapabilities()
    model = CommandModel(commands)
    service = AdminChatService(
        capabilities=capabilities,
        conversations=AdminConversationRegistry(),
        limiter=Limiter(),
        settings_factory=lambda: settings,
        model_factory=lambda _settings: model,
    )
    return service, capabilities


@pytest.mark.parametrize("pattern", ["hierarchical", "orchestrator", "decentralized"])
def test_admin_chat_requires_same_actor_explicit_confirmation_and_is_idempotent(pattern):
    service, capabilities = _service([
        AdminCommand(intent="write", capability="customers.create", arguments={"display_name": "Cliente"}),
    ])
    principal = Principal(actor_id=7, role="ADMIN")
    proposed = service.execute(principal=principal, pattern=pattern, message="Registra un cliente")

    assert proposed.proposal["status"] == "PENDING_CONFIRMATION"
    assert capabilities.executed == []
    confirmed = service.execute(
        principal=principal, pattern=pattern, message="Sí, confirmo",
        conversation_id=proposed.conversation_id,
    )
    repeated = service.execute(
        principal=principal, pattern=pattern, message="confirmo",
        conversation_id=proposed.conversation_id,
    )
    assert confirmed.result == {"updated": True}
    assert repeated.result == confirmed.result
    assert len(capabilities.executed) == 1
    assert capabilities.executed[0][2] == 7

    with pytest.raises(CapabilityError) as error:
        service.execute(
            principal=Principal(actor_id=8, role="ADMIN"), pattern=pattern,
            message="confirmo", conversation_id=proposed.conversation_id,
        )
    assert error.value.code == "conversation_not_found"


@pytest.mark.parametrize("pattern", ["hierarchical", "orchestrator", "decentralized"])
def test_admin_read_needs_no_proposal_and_customer_role_is_denied(pattern):
    service, capabilities = _service([
        AdminCommand(intent="read", capability="customers.list", arguments={"limit": 5}),
    ])
    result = service.execute(
        principal=Principal(actor_id=7, role="ADMIN"), pattern=pattern,
        message="Lista los clientes",
    )
    assert result.proposal is None
    assert capabilities.reads == [("customers.list", {"limit": 5})]
    assert capabilities.executed == []

    with pytest.raises(CapabilityError) as error:
        service.execute(
            principal=Principal(actor_id=12, role="CUSTOMER", commercial_customer_id=9),
            pattern=pattern, message="Lista clientes",
        )
    assert error.value.code == "forbidden"


@pytest.mark.parametrize("pattern", ["hierarchical", "orchestrator", "decentralized"])
def test_ambiguous_admin_confirmation_discards_without_executing(pattern):
    service, capabilities = _service([
        AdminCommand(intent="write", capability="customers.create", arguments={"display_name": "Cliente"}),
        AdminCommand(intent="help"),
    ])
    principal = Principal(actor_id=7, role="ADMIN")
    proposed = service.execute(principal=principal, pattern=pattern, message="Registra un cliente")
    followup = service.execute(
        principal=principal, pattern=pattern, message="tal vez sí",
        conversation_id=proposed.conversation_id,
    )
    assert followup.proposal is None
    assert capabilities.executed == []


@pytest.mark.parametrize("pattern", ["hierarchical", "orchestrator", "decentralized"])
def test_admin_can_cancel_pending_write_without_side_effects(pattern):
    service, capabilities = _service([
        AdminCommand(intent="write", capability="customers.create", arguments={"display_name": "Cliente"}),
        AdminCommand(intent="help"),
    ])
    principal = Principal(actor_id=7, role="ADMIN")
    proposed = service.execute(principal=principal, pattern=pattern, message="Registra un cliente")

    cancelled = service.execute(
        principal=principal,
        pattern=pattern,
        message="Cancelo la propuesta",
        conversation_id=proposed.conversation_id,
    )

    assert cancelled.proposal["status"] == "CANCELLED"
    assert "no se hicieron cambios" in cancelled.reply.casefold()
    assert capabilities.executed == []

    # A later confirmation cannot revive the cancelled write.
    with pytest.raises(CapabilityError) as error:
        service.execute(
            principal=principal,
            pattern=pattern,
            message="confirmo",
            conversation_id=proposed.conversation_id,
        )
    assert error.value.code == "proposal_not_found"


class Transcriber:
    def __init__(self, text="confirmo"):
        self.text, self.calls = text, 0

    def transcribe(self, _audio, *, content_type):
        self.calls += 1
        return TranscriptionResult(self.text)


@pytest.mark.parametrize("pattern", ["hierarchical", "orchestrator", "decentralized"])
def test_admin_voice_can_confirm_only_admin_proposal_and_audio_idempotency_is_role_scoped(pattern):
    service, capabilities = _service([
        AdminCommand(intent="write", capability="customers.create", arguments={"display_name": "Cliente"}),
    ])
    principal = Principal(actor_id=7, role="ADMIN")
    proposed = service.execute(principal=principal, pattern=pattern, message="Registra un cliente")
    transcriber = Transcriber("Confirmo")
    audio = SendAudioChatMessage(transcriber, None, AudioRequestRegistry())
    common = dict(
        customer_id=7, audio=b"recording", content_type="audio/webm", duration_ms=1000,
        pattern=pattern, request_id="00000000-0000-0000-0000-000000000111",
        conversation_id=proposed.conversation_id,
    )
    admin_result = audio.execute(
        **common, principal_role="ADMIN",
        message_handler=lambda transcript: service.execute(
            principal=principal, pattern=pattern, message=transcript,
            conversation_id=proposed.conversation_id,
        ),
    )
    assert admin_result.turn.result == {"updated": True}
    assert len(capabilities.executed) == 1

    # Same actor/request ID/audio in the CUSTOMER namespace is a separate request
    # and reaches the client pattern, never the ADMIN proposal handler.
    customer_result = audio.execute(
        **common, principal_role="CUSTOMER",
        message_handler=lambda transcript: PatternReply(reply="cliente:" + transcript),
    )
    assert customer_result.turn.reply == "cliente:Confirmo"
    assert transcriber.calls == 2
