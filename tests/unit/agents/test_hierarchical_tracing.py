import json

import pytest

from app.agents.jerarquico.trace import traced_node, traced_tool


def test_hierarchical_trace_contains_only_execution_metadata(tmp_path, monkeypatch):
    trace_path = tmp_path / "trace.jsonl"
    monkeypatch.setenv("HIERARCHICAL_TRACE_PATH", str(trace_path))

    root = traced_node(
        "customer_care_supervisor",
        lambda _state: {"route": "informational"},
        root=True,
    )
    result = root(
        {
            "messages": ["private customer message"],
            "customer_email": "customer@example.test",
        }
    )
    traced_tool(result, "inventory_lookup", lambda: ["private product data"])

    records = [json.loads(line) for line in trace_path.read_text().splitlines()]
    assert [record["event"] for record in records] == [
        "start",
        "success",
        "start",
        "success",
    ]
    assert {record["execution_id"] for record in records} == {result["trace_id"]}
    assert all(
        set(record) == {"timestamp", "execution_id", "name", "kind", "event"}
        for record in records
    )
    trace_text = trace_path.read_text()
    assert "private customer message" not in trace_text
    assert "customer@example.test" not in trace_text
    assert "private product data" not in trace_text


def test_hierarchical_trace_marks_tool_errors_without_exception_text(
    tmp_path, monkeypatch
):
    trace_path = tmp_path / "trace.jsonl"
    monkeypatch.setenv("HIERARCHICAL_TRACE_PATH", str(trace_path))

    with pytest.raises(RuntimeError, match="private exception"):
        traced_tool(
            {"trace_id": "execution-1"},
            "warranty_lookup",
            lambda: (_ for _ in ()).throw(RuntimeError("private exception")),
        )

    records = [json.loads(line) for line in trace_path.read_text().splitlines()]
    assert [record["event"] for record in records] == ["start", "error"]
    assert records[1]["error_type"] == "RuntimeError"
    assert "sqlstate" not in records[1]
    assert "private exception" not in trace_path.read_text()


def test_hierarchical_trace_keeps_only_safe_postgres_sqlstate(tmp_path, monkeypatch):
    trace_path = tmp_path / "trace.jsonl"
    monkeypatch.setenv("HIERARCHICAL_TRACE_PATH", str(trace_path))

    class DatabaseFailure(Exception):
        sqlstate = "23505"

    with pytest.raises(DatabaseFailure):
        traced_tool(
            {"trace_id": "execution-2"},
            "warranty_write",
            lambda: (_ for _ in ()).throw(DatabaseFailure("private row contents")),
        )

    records = [json.loads(line) for line in trace_path.read_text().splitlines()]
    assert records[-1]["error_type"] == "DatabaseFailure"
    assert records[-1]["sqlstate"] == "23505"
    assert "private row contents" not in trace_path.read_text()

