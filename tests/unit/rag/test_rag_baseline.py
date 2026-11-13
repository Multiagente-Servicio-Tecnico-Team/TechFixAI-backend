"""Contratos de la evaluación: referencias, ausencias, caché y reanudación."""
import asyncio
from copy import deepcopy
from types import SimpleNamespace

import pytest

from rag_eval.baseline_state import digest, metric_eligibility, select_cases


def example_row(**overrides):
    return {"id": "case", "route": "technical", "category": "technical", "answerable": True,
            "user_input": "¿Qué falla?", "reference": "La memoria RAM tiene una falla.",
            "response": "La memoria RAM tiene una falla.", "retrieved_contexts": ["La RAM falla."],
            "metrics": {}, "generation_status": "ok", "retrieval_status": "context", **overrides}


def test_retrieval_can_be_scored_even_if_generation_failed():
    row = example_row(response=None, generation_status="api_error")
    assert metric_eligibility("context_precision", row) == ("pending", None)
    assert metric_eligibility("context_recall", row) == ("pending", None)
    assert metric_eligibility("faithfulness", row) == ("pending", "no_response")


def test_response_without_context_keeps_reference_metrics_applicable():
    row = example_row(retrieved_contexts=[])
    assert metric_eligibility("faithfulness", row) == ("not_applicable", "no_context")
    for name in ("factual_correctness", "response_relevancy", "text"):
        assert metric_eligibility(name, row) == ("pending", None)


def test_controls_do_not_receive_invented_reference_scores():
    row = example_row(answerable=False, reference="", retrieved_contexts=[])
    assert metric_eligibility("text", row) == ("not_applicable", "no_reference")
    assert metric_eligibility("context_recall", row) == ("not_applicable", "no_reference")


def test_component_without_output_is_not_mislabeled_as_pending_generation():
    row = example_row(response=None, retrieved_contexts=[], generation_status="no_context")
    for name in ("text", "response_relevancy", "factual_correctness"):
        assert metric_eligibility(name, row) == ("not_applicable", "component_produced_no_response")


def test_selection_preserves_dataset_order_and_rejects_unknown_ids():
    rows = [{"id": x} for x in ("a", "b", "c")]
    assert select_cases(rows, ["c", "a"], 1) == [{"id": "a"}]
    with pytest.raises(ValueError):
        select_cases(rows, ["typo"])
    with pytest.raises(ValueError):
        select_cases(rows, limit=-1)


def test_spanish_tokenizer_preserves_diacritics_codes_and_decomposed_unicode():
    from rag_eval.text_metrics import SpanishTokenizer
    tokens = SpanishTokenizer().tokenize("Diagnóstico: daño, conexión 0x0000007B SSD_1TB y conexio\u0301n.")
    assert tokens == ["diagnóstico", "daño", "conexión", "0x0000007b", "ssd_1tb", "y", "conexión"]


def test_rouge_keeps_negation_and_exact_text_matches():
    pytest.importorskip("rouge_score", exc_type=ImportError)
    from rag_eval.text_metrics import score_rouge
    reference = "No reemplazar la batería dañada sin evaluación."
    assert score_rouge(reference, reference)["rougeL"]["f1"] == 1
    assert score_rouge(reference, "Reemplazar la batería dañada sin evaluación.")["rouge1"]["recall"] < 1


def test_bleu_uses_corpus_statistics_instead_of_sentence_average():
    pytest.importorskip("sacrebleu", exc_type=ImportError)
    from rag_eval.text_metrics import corpus_bleu
    rows = [example_row(reference="uno dos tres cuatro cinco seis", response="uno dos tres cuatro cinco seis"),
            example_row(reference="siete ocho nueve diez", response="otros términos distintos")]
    corpus = corpus_bleu(rows)["bleu4"]
    average = sum(corpus_bleu([row])["bleu4"]["value"] for row in rows) / 2
    assert corpus["value"] != pytest.approx(average)
    assert corpus["evaluated"] == 2
    assert "tok:13a" in corpus["signature"]


def test_historical_120b_is_rejected_for_20b_generation():
    pytest.importorskip("ragas", exc_type=ImportError)
    from rag_eval.baseline_state import merge_historical
    config = {"dataset_sha256": "d", "source_sha256": {}, "model": "20b", "generator_transport": "backend",
              "native_model_profile": {}, "retrieval_mode": "lexical", "retrieval_limit": 3}
    payload = {"metadata": {"generation_config": config}, "results": []}
    evidence = {"metadata": {**config, "model": "120b"}, "results": []}
    with pytest.raises(ValueError, match="histórica"):
        merge_historical(payload, evidence, "historical")


def test_generation_configuration_changes_are_rejected():
    from rag_eval.baseline_state import validate_run
    config = {"model": "20b"}
    payload = {"metadata": {"format": "techfix_rag_baseline_v1", "generation_config": config,
                            "generation_fingerprint": digest(config)}, "results": []}
    with pytest.raises(ValueError, match="configuración de generación"):
        validate_run(payload, {"model": "120b"})


def test_context_recorder_forwards_original_messages_and_method():
    from rag_eval.baseline import ContextRecordingModel
    forwarded = []
    class Model:
        def with_structured_output(self, schema, *, method):
            forwarded.append((schema, method))
            return self
        def invoke(self, messages):
            forwarded.append(messages)
            return "answer"
    observations = {}
    messages = [SimpleNamespace(type="system", content="Guías RAG recuperadas:\nfragmento"),
                SimpleNamespace(type="human", content="pregunta")]
    model = ContextRecordingModel(Model(), "fragmento", observations).with_structured_output(dict, method="json_mode")
    assert model.invoke(messages) == "answer"
    assert forwarded == [(dict, "json_mode"), messages]
    assert observations["context"] == "fragmento"
    with pytest.raises(ValueError):
        ContextRecordingModel(Model(), "otro", {}).invoke(messages)


def test_resume_does_not_generate_completed_cases(tmp_path, monkeypatch):
    pytest.importorskip("ragas", exc_type=ImportError)
    from rag_eval import baseline, native_provider, runtime
    from rag_eval import baseline_report
    from rag_eval.baseline_state import new_case
    sample = {"id": "technical_case", "route": "technical", "answerable": True, "user_input": "pregunta", "reference": "referencia"}
    prepared = {"contexts": ["fragmento"], "context": "fragmento"}
    item = new_case(sample, {**prepared, "source_ids": []})
    item.update(generation_status="ok", response="respuesta")
    config = {"model": "fixture"}
    payload = {"metadata": {"generation_config": config, "historical_imports": [], "judge_model": "judge"}, "results": [item]}
    (tmp_path / "results.json").write_text("{}")
    monkeypatch.setattr(baseline, "local_directory", lambda p: tmp_path)
    monkeypatch.setattr(baseline, "generation_config", lambda s: config)
    monkeypatch.setattr(baseline, "load_dataset", lambda p: ({}, [sample], "hash"))
    monkeypatch.setattr(baseline, "load_run", lambda *a: payload)
    monkeypatch.setattr(runtime, "prepare_case", lambda s: prepared)
    monkeypatch.setattr(runtime, "generate_case", lambda *a: pytest.fail("No regenerar respuestas terminadas"))
    monkeypatch.setattr(native_provider, "create_native_model", lambda *a: pytest.fail("No crear LLM al reanudar terminados"))
    monkeypatch.setattr(baseline_report, "save_baseline", lambda *a: None)
    args = SimpleNamespace(run=tmp_path, judge_model="judge", reuse_run=None, only=None, limit=0, prepare_only=False)
    assert baseline.generate(args) == 0
    assert len(payload["results"]) == 1
    assert payload["metadata"]["generation_calls_last_command"] == 0


def test_extended_metrics_api_uses_reference_precision_and_f1():
    pytest.importorskip("ragas", exc_type=ImportError)
    from ragas.metrics.collections import ContextPrecisionWithReference
    from rag_eval.extended_metrics import create_extended_metrics
    from rag_eval.providers import CompletionStore, StrictGroqJudge
    # La construcción no necesita cliente ni llamadas: las propiedades se inspeccionan.
    judge = StrictGroqJudge(None, "fixture", None)
    metrics = create_extended_metrics(judge)
    assert isinstance(metrics["context_precision"], ContextPrecisionWithReference)
    assert metrics["factual_correctness"].mode == "f1"
    assert metrics["context_precision"].prompt.examples == []


def test_relevance_uses_three_cache_slots_and_reuses_them_on_resume(tmp_path):
    pytest.importorskip("ragas", exc_type=ImportError)
    from ragas.embeddings.base import BaseRagasEmbedding
    from rag_eval.extended_metrics import create_extended_metrics
    from rag_eval.providers import CompletionStore, StrictGroqJudge
    class Embeddings(BaseRagasEmbedding):
        def embed_text(self, text, **kwargs):
            return [1.0, 0.0]
        async def aembed_text(self, text, **kwargs):
            return self.embed_text(text)
    calls = []
    async def fake_create(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(
            content='{"question":"¿Qué falla?","noncommittal":0}'))])
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create)))
    store = CompletionStore(tmp_path)
    metric = create_extended_metrics(StrictGroqJudge(client, "fixture", store), Embeddings())["response_relevancy"]
    first = asyncio.run(metric.ascore(user_input="¿Qué falla?", response="Falla la RAM."))
    second = asyncio.run(metric.ascore(user_input="¿Qué falla?", response="Falla la RAM."))
    assert first.value == second.value == 1
    assert len(calls) == 3
    assert calls[0] == calls[1] == calls[2]
    assert store.calls == 3 and store.hits == 3


def test_summary_exposes_missing_scores_and_does_not_hide_retrieval_failure():
    from rag_eval.baseline_report import summarize_group
    row = example_row(retrieved_contexts=[], generation_status="api_error", response=None, retrieval_status="no_context")
    summary = summarize_group([row], include_text=False)
    assert summary["answerable_with_context"] == 0
    assert summary["generation_errors"] == 1
    assert summary["metrics"]["faithfulness"]["mean"] is None
    assert summary["metrics"]["faithfulness"]["evaluated"] == 0
