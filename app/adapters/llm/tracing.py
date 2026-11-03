"""Trazas de LangSmith para los patrones: entradas y salidas ocultas y errores redactados."""
from contextlib import AbstractContextManager, nullcontext
from typing import Any

from langsmith import Client, tracing_context

from app.settings import Settings, load_settings


def get_trace_context(settings: Settings | None = None) -> AbstractContextManager[None]:
    settings = settings or load_settings()
    if not settings.langsmith_tracing:
        return nullcontext()
    if not settings.langsmith_api_key:
        raise RuntimeError("LANGSMITH_API_KEY es necesaria cuando LANGSMITH_TRACING=true.")
    client = Client(
        api_key=settings.langsmith_api_key,
        hide_inputs=settings.langsmith_hide_inputs,
        hide_outputs=settings.langsmith_hide_outputs,
        anonymizer=redact_trace_error,
    )
    return tracing_context(enabled=True, project_name=settings.langsmith_project, client=client)


def redact_trace_error(values: dict[str, Any]) -> dict[str, Any]:
    if isinstance(values.get("error"), str):
        return {**values, "error": "Provider error details redacted."}
    return values
