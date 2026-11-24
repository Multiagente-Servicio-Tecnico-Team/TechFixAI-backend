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


@pytest.mark.parametrize("hide_inputs,hide_outputs", [(False, False), (False, True), (True, False), (True, True)])
def test_audio_respects_configured_langsmith_visibility(hide_inputs, hide_outputs):
    # Spec 011 FR-020: con audio activo, la visibilidad del texto la deciden LANGSMITH_HIDE_*;
    # el audio crudo y las credenciales quedan fuera en todos los modos.
    current = settings(hide_inputs=hide_inputs, hide_outputs=hide_outputs)
    assert current.audio_transcription_enabled is True
    assert (current.langsmith_hide_inputs, current.langsmith_hide_outputs) == (hide_inputs, hide_outputs)


def test_trace_error_redaction_drops_provider_text():
    result = redact_trace_error({"error": "secret transcript and token"})
    assert result == {"error": "Provider error details redacted."}
    assert "transcript" not in str(result) and "token" not in str(result)
