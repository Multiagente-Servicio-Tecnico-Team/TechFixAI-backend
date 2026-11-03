import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from langgraph.graph import END, START, StateGraph

from app.agents.sales import DEMO_REQUEST, QuoteState, build_sales_graph
from app.tracing import invoke_traced


def test_correlated_agents_and_tools(tmp_path, monkeypatch):
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    path = tmp_path / "trace.jsonl"
    request = {**DEMO_REQUEST, "diagnosis": "password=private-secret"}
    result, execution_id = invoke_traced(build_sales_graph(), {"request": request}, path)
    records = [json.loads(line) for line in path.read_text().splitlines()]
    assert {r["execution_id"] for r in records} == {execution_id}
    assert {"sales_agent", "lookup_catalog"} <= {r["name"] for r in records}
    assert any(r["kind"] == "tool" and r["parent_run_id"] for r in records)
    assert "private-secret" not in path.read_text()
    assert result["quote"]["total"] == "260.00"


def test_failure_excludes_exception_secret(tmp_path):
    def fail(state):
        raise RuntimeError("password=never-record-me bearer secret")
    builder = StateGraph(QuoteState)
    builder.add_node("failure_probe", fail)
    builder.add_edge(START, "failure_probe")
    builder.add_edge("failure_probe", END)
    path = tmp_path / "trace.jsonl"
    with pytest.raises(RuntimeError):
        invoke_traced(builder.compile(), {"request": {}}, path)
    records = [json.loads(line) for line in path.read_text().splitlines()]
    assert any(r["event"] == "error" and r["name"] == "failure_probe" for r in records)
    assert len({r["execution_id"] for r in records}) == 1
    assert "never-record-me" not in path.read_text()
    assert "password" not in path.read_text()


def test_concurrent_execution_isolation(tmp_path):
    path = tmp_path / "trace.jsonl"
    graph = build_sales_graph()
    with ThreadPoolExecutor(max_workers=3) as executor:
        results = list(executor.map(lambda _: invoke_traced(graph, {"request": DEMO_REQUEST}, path), range(3)))
    ids = {execution_id for _, execution_id in results}
    records = [json.loads(line) for line in path.read_text().splitlines()]
    assert len(ids) == 3
    assert {r["execution_id"] for r in records} == ids
    for record in records:
        if record["parent_run_id"]:
            assert any(parent["run_id"] == record["parent_run_id"] and parent["execution_id"] == record["execution_id"] for parent in records)
