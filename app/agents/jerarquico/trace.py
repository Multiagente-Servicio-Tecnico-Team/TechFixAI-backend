"""Safe per-turn traces for the hierarchical graph (no inputs or outputs)."""

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Callable
from uuid import uuid4


AGENT_NAMES = {
    "customer_care_supervisor",
    "orchestrator_supervisor",
    "reception_agent",
    "commercial_team_supervisor",
    "technical_team_supervisor",
    "operations_team_supervisor",
    "faq_agent",
    "out_of_scope_agent",
    "technical_support_agent",
    "software_support_agent",
    "knowledge_retrieval",
    "warehouse_agent",
    "sales_agent",
    "billing_agent",
    "logistics_agent",
    "warranty_agent",
    "refund_agent",
    "order_completion_agent",
    "persist_diagnosis",
    "quote_suggestion_response",
}
TOOL_NAMES = {
    "inventory_lookup",
    "warranty_lookup",
    "accepted_quote_write",
    "warranty_claim_write",
    "warranty_write",
    "logistics_record_write",
    "ticket_quote_write",
    "intake_ticket_write",
    "ticket_diagnosis_write",
    "customer_lookup",
    "domain_guard",
    "ticket_cancel",
    "refund_payment_lookup",
    "refund_request_write",
    "direct_sale_quote_acceptance",
}
_trace_lock = Lock()


def _trace_path() -> Path:
    return Path(
        os.getenv(
            "HIERARCHICAL_TRACE_PATH",
            ".local/hierarchical-traces.jsonl",
        )
    )


def trace_event(
    execution_id: str,
    name: str,
    event: str,
    *,
    kind: str = "agent",
    error_type: str | None = None,
    sqlstate: str | None = None,
) -> None:
    allowed_names = AGENT_NAMES if kind == "agent" else TOOL_NAMES
    if name not in allowed_names or event not in {"start", "success", "error"}:
        raise ValueError("Evento de trazabilidad no admitido.")
    if kind not in {"agent", "tool"}:
        raise ValueError("Tipo de evento de trazabilidad no admitido.")
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "execution_id": execution_id,
        "name": name,
        "kind": kind,
        "event": event,
    }
    if event == "error":
        if error_type and re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", error_type):
            record["error_type"] = error_type
        if sqlstate and re.fullmatch(r"[0-9A-Z]{5}", sqlstate):
            record["sqlstate"] = sqlstate
    path = _trace_path()
    with _trace_lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=True) + "\n")


def traced_node(name: str, node: Callable[..., dict[str, Any]], *, root: bool = False):
    if name not in AGENT_NAMES:
        raise ValueError("Nombre de agente no permitido en la traza.")

    def run(state: dict[str, Any]) -> dict[str, Any]:
        execution_id = str(uuid4()) if root else state.get("trace_id")
        if not isinstance(execution_id, str):
            execution_id = str(uuid4())
        trace_event(execution_id, name, "start")
        try:
            result = node(state)
        except Exception as exc:
            trace_event(
                execution_id,
                name,
                "error",
                error_type=type(exc).__name__,
                sqlstate=_sqlstate(exc),
            )
            raise
        trace_event(execution_id, name, "success")
        if root:
            return {**result, "trace_id": execution_id}
        return result

    return run


def traced_tool(
    state: dict[str, Any],
    name: str,
    operation: Callable[[], Any],
) -> Any:
    execution_id = state.get("trace_id")
    if not isinstance(execution_id, str):
        execution_id = str(uuid4())
    trace_event(execution_id, name, "start", kind="tool")
    try:
        result = operation()
    except Exception as exc:
        trace_event(
            execution_id,
            name,
            "error",
            kind="tool",
            error_type=type(exc).__name__,
            sqlstate=_sqlstate(exc),
        )
        raise
    trace_event(execution_id, name, "success", kind="tool")
    return result


def _sqlstate(exc: Exception) -> str | None:
    original = getattr(exc, "orig", None)
    for candidate in (original, exc):
        if candidate is None:
            continue
        value = getattr(candidate, "sqlstate", None) or getattr(
            candidate, "pgcode", None
        )
        if isinstance(value, str) and re.fullmatch(r"[0-9A-Z]{5}", value):
            return value
    return None
