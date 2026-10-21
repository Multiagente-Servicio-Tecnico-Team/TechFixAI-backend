from decimal import Decimal
from unittest.mock import patch

from app.adapters.llm.tracing import get_trace_context, redact_trace_error
from app.settings import Settings


def settings(*, tracing=False):
    return Settings(
        groq_api_key=None,
        groq_model=None,
        database_url=None,
        langsmith_api_key="test-langsmith-key" if tracing else None,
        langsmith_tracing=tracing,
        langsmith_project="pattern-tests",
        langsmith_hide_inputs=True,
        langsmith_hide_outputs=True,
        labor_maintenance_price=Decimal("40.00"),
        labor_diagnosis_price=Decimal("50.00"),
    )


def test_trace_error_redaction_does_not_preserve_provider_text():
    result = redact_trace_error(
        {"error": "DATABASE_URL=private-value", "run_id": "trace-id"}
    )

    assert result == {
        "error": "Provider error details redacted.",
        "run_id": "trace-id",
    }
    assert "private-value" not in str(result)


def test_trace_context_uses_langsmith_project_and_hides_inputs_and_outputs():
    with (
        patch("app.adapters.llm.tracing.Client") as client_factory,
        patch("app.adapters.llm.tracing.tracing_context", return_value="trace-context") as trace_factory,
    ):
        result = get_trace_context(settings(tracing=True))

    assert result == "trace-context"
    client_factory.assert_called_once()
    assert client_factory.call_args.kwargs["hide_inputs"] is True
    assert client_factory.call_args.kwargs["hide_outputs"] is True
    trace_factory.assert_called_once()
    assert trace_factory.call_args.kwargs["enabled"] is True
    assert trace_factory.call_args.kwargs["project_name"] == "pattern-tests"


def test_tracing_can_be_disabled():
    with patch("app.adapters.llm.tracing.tracing_context") as trace_factory:
        context = get_trace_context(settings())

    assert context.__class__.__name__ == "nullcontext"
    trace_factory.assert_not_called()
