from decimal import Decimal

import pytest

from app.adapters.llm.tracing import redact_trace_error
from app.settings import Settings


def settings(*, hide_inputs, hide_outputs):
    return Settings(
        groq_api_key=None, groq_model=None, database_url=None, langsmith_api_key="trace-key",
        langsmith_tracing=True, langsmith_project="test", langsmith_hide_inputs=hide_inputs,
        langsmith_hide_outputs=hide_outputs, labor_maintenance_price=Decimal("35"),
        labor_diagnosis_price=Decimal("50"), audio_transcription_enabled=True,
    )


def test_audio_requires_both_langsmith_payloads_to_be_hidden():
    with pytest.raises(RuntimeError):
        settings(hide_inputs=False, hide_outputs=True).validate_audio_privacy()
    with pytest.raises(RuntimeError):
        settings(hide_inputs=True, hide_outputs=False).validate_audio_privacy()
    settings(hide_inputs=True, hide_outputs=True).validate_audio_privacy()


def test_trace_error_redaction_drops_provider_text():
    result = redact_trace_error({"error": "secret transcript and token"})
    assert result == {"error": "Provider error details redacted."}
    assert "transcript" not in str(result) and "token" not in str(result)
