"""Pruebas aisladas del evaluador; ninguna llamada a Groq o PostgreSQL."""
import asyncio
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import httpx
import pytest
from pydantic import BaseModel

pytest.importorskip("ragas", exc_type=ImportError)

from rag_eval.evaluate_project import BASE, ROOT, load_dataset
from rag_eval.providers import CompletionStore, StrictGroqJudge, cache_key, retry_delay, safe_error, schema_format, validate_verdicts
from rag_eval.reporting import save_report, summarize


class Verdict(BaseModel):
    verdict: int
    reason: str


class NestedVerdict(BaseModel):
    items: list[Verdict]


def test_missing_scores_do_not_disappear_from_coverage_or_become_zero(tmp_path):
    rows = [
        {"id": "valid", "route": "technical", "answerable": True, "status": "ok", "context_count": 1, "faithfulness": 0.5, "context_precision": 1.0, "context_recall": 0.0},
        {"id": "missing", "route": "technical", "answerable": True, "status": "no_context", "context_count": 0, "faithfulness": None},
        {"id": "error", "route": "faq", "answerable": True, "status": "metric_error", "context_count": 1, "faithfulness": None, "failed_metrics": [{"metric": "faithfulness", "http_status": 400}]},
        {"id": "control", "route": "faq", "answerable": False, "status": "expected_abstention", "context_count": 0},
    ]
    summary = save_report(tmp_path, rows, {"planned_cases": 4})
    assert summary["metrics"]["faithfulness"] == {"mean": 0.5, "std_population": 0.0, "evaluated": 1}
    assert summary["metrics"]["context_recall"]["mean"] == 0.0
    assert summary["answerable_with_context"] == 2
    assert summary["answerable"] == 3
    assert summary["operational_errors"] == 1
    stored = json.loads((tmp_path / "results.json").read_text(encoding="utf-8"))
    assert stored["results"][1]["faithfulness"] is None
    assert "metric_error" in (tmp_path / "results.csv").read_text(encoding="utf-8-sig")


def test_nan_and_boolean_are_not_valid_scores_in_summary():
    rows = [{"answerable": True, "context_count": 1, "status": "metric_error", "faithfulness": float("nan"), "context_precision": True}]
    summary = summarize(rows, 1)
    assert summary["metrics"]["faithfulness"]["evaluated"] == 0
    assert summary["metrics"]["context_precision"]["evaluated"] == 0


def test_dataset_covers_cases_and_references_are_verified(tmp_path):
    dataset, rows, digest = load_dataset(BASE / "dataset_project.json")
    assert len(rows) == 30
    assert sum(r["answerable"] for r in rows) == 28
    assert len(digest) == 64
    assert len([r for r in rows if r["route"] == "technical" and r["answerable"]]) == 20
    altered = copy.deepcopy(dataset)
    altered["rows"][0]["reference"] = "Un dato inventado que no aparece en la fuente."
    path = tmp_path / "altered.json"
    path.write_text(json.dumps(altered), encoding="utf-8")
    with pytest.raises(ValueError):
        load_dataset(path)


def test_strict_schema_requires_nested_fields_and_disallows_extras():
    response_format = schema_format(NestedVerdict)
    assert response_format["json_schema"]["strict"] is True
    schema = response_format["json_schema"]["schema"]
    assert schema["additionalProperties"] is False
    assert schema["$defs"]["Verdict"]["additionalProperties"] is False
    assert set(schema["$defs"]["Verdict"]["required"]) == {"reason", "verdict"}
    with pytest.raises(ValueError):
        validate_verdicts(Verdict(verdict=2, reason="invalid"))


def test_strict_judge_uses_cache_and_never_sends_credentials_in_payload(tmp_path):
    calls = []
    async def create(**payload):
        calls.append(payload)
        return SimpleNamespace(choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content='{"verdict":1,"reason":"Supported"}'))])
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    store = CompletionStore(tmp_path)
    judge = StrictGroqJudge(client, "model-for-test", store)
    async def exercise():
        first = await judge.agenerate("Synthetic context", Verdict)
        second = await judge.agenerate("Synthetic context", Verdict)
        assert first.verdict == second.verdict == 1
    asyncio.run(exercise())
    assert len(calls) == 1
    assert store.hits == 1
    assert calls[0]["response_format"]["json_schema"]["strict"] is True
    assert calls[0]["max_completion_tokens"] == 4096
    assert "api_key" not in calls[0]
    assert cache_key({"b": 1, "a": 2}) == cache_key({"a": 2, "b": 1})
    assert cache_key({"model": "a"}) != cache_key({"model": "b"})


def test_truncated_judgment_is_not_cached(tmp_path):
    async def create(**payload):
        return SimpleNamespace(choices=[SimpleNamespace(finish_reason="length", message=SimpleNamespace(content='{"verdict":1,"reason":"x"}'))])
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    judge = StrictGroqJudge(client, "model-for-test", CompletionStore(tmp_path))
    with pytest.raises(ValueError):
        asyncio.run(judge.agenerate("Synthetic input", Verdict))
    assert list(tmp_path.iterdir()) == []


def test_redacted_errors_and_bounded_transient_retries():
    from openai import BadRequestError, RateLimitError
    response = httpx.Response(400, request=httpx.Request("POST", "https://example.invalid"))
    error = BadRequestError("SECRET INPUT", response=response, body={"error": {"message": "SECRET KEY", "code": "json_validate_failed"}})
    redacted = safe_error(error)
    assert "SECRET" not in json.dumps(redacted)
    assert redacted["code"] == "json_validate_failed"
    assert retry_delay(error, 0) is None
    response = httpx.Response(429, headers={"retry-after": "9999"}, request=httpx.Request("POST", "https://example.invalid"))
    limited = RateLimitError("SECRET", response=response, body={})
    assert retry_delay(limited, 0) == 45


def test_dry_run_requires_no_api_key_and_creates_no_run_directory():
    directory = ROOT / ".local" / "ragas"
    before = {p.name for p in directory.glob("project-*")}
    env = {**os.environ, "GROQ_API_KEY": "", "GROQ_MODEL": "", "RAG_RETRIEVAL_MODE": "lexical"}
    result = subprocess.run([sys.executable, "-m", "rag_eval.evaluate_project", "--dry-run"], cwd=ROOT, env=env, capture_output=True, timeout=45)
    assert result.returncode == 0, result.stdout.decode(errors="replace")
    assert b"30 casos" in result.stdout
    assert before == {p.name for p in directory.glob("project-*")}

def test_daily_quota_stops_retries_and_is_redacted():
    from openai import RateLimitError
    from rag_eval.providers import daily_quota
    response = httpx.Response(429, headers={"retry-after": "600"}, request=httpx.Request("POST", "https://example.invalid"))
    error = RateLimitError("PRIVATE ACCOUNT", response=response, body={"error": {"message": "PRIVATE ACCOUNT reached tokens per day", "code": "rate_limit_exceeded"}})
    assert daily_quota(error) == "daily_tokens"
    assert retry_delay(error, 0) is None
    assert safe_error(error)["quota"] == "daily_tokens"
    assert "PRIVATE" not in json.dumps(safe_error(error))
    rows = [{"answerable": True, "context_count": 1, "status": "quota_exhausted"}]
    assert summarize(rows, 1)["operational_errors"] == 1
