"""Comparación local de umbrales técnicos sin cambiar el valor predeterminado."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import inspect
import json
from pathlib import Path
import re
from statistics import mean
from types import SimpleNamespace
from unittest.mock import patch

from rag_eval.baseline_state import (
    BASE, ROOT, RAGAS_METRICS, digest, file_digest, generation_config, load_dataset,
    load_run, local_directory, new_case, new_run, versions,
)
from rag_eval.evaluate_project import isolate_process, source_manifest

THRESHOLDS = (0.34, 0.33, 0.30, 0.29)
FAILED_IDS = ("technical_02_natural", "technical_03_natural", "technical_04_natural")


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")


def baseline_hashes(directory):
    return {p.relative_to(directory).as_posix(): file_digest(p) for p in directory.rglob("*") if p.is_file()}


def assert_baseline_unchanged(directory, expected):
    if baseline_hashes(directory) != expected:
        raise ValueError("Cambió la evidencia de baseline-v1-final")


def candidate_details(query, documents, filters):
    """Expone el cálculo léxico original; la selección la hace retrieve_documents."""
    from app.rag import retriever
    query_norm = retriever._normalize(query)
    tokens = {t for t in re.findall(r"[a-z0-9]{3,}", query_norm) if t not in retriever._QUERY_STOP_WORDS}
    result = []
    for document in documents:
        meta = retriever._metadata(document)
        normalized = retriever._normalize(" ".join((document.page_content, meta.get("title", ""), meta.get("section", ""))))
        content_tokens = set(re.findall(r"[a-z0-9]{3,}", normalized))
        refs = set(meta.get("source_refs", "").split(",")) | {meta.get("source_id", "")}
        allowed = {"source": bool(refs & filters["allowed_sources"]),
                   "area": meta.get("area") in filters["allowed_areas"],
                   "trust": meta.get("trust_level") in filters["allowed_trust_levels"]}
        overlap = tokens & content_tokens
        coverage = len(overlap) / max(len(tokens), 1)
        result.append({"source_id": meta["source_id"], "source_path": meta["source_path"],
                       "title": meta["title"], "content": document.page_content,
                       "matched_tokens": sorted(overlap), "query_tokens": sorted(tokens),
                       "overlap": len(overlap), "query_token_count": len(tokens),
                       "coverage": coverage, "coverage_repr": repr(coverage), "filters": allowed})
    return result


@contextmanager
def technical_threshold(value, observations=None):
    """Solo sustituye la referencia del adaptador técnico, nunca la de FAQ."""
    from app.agents.jerarquico import retriever as technical
    original = technical.retrieve_documents

    def scoped(query, **kwargs):
        if observations is not None:
            observations.append({"query": query, "candidates": candidate_details(query, kwargs["documents"], kwargs)})
        return original(query, lexical_min_coverage=value, **kwargs)

    with patch.object(technical, "retrieve_documents", scoped):
        yield


def experiment_config(settings, threshold, baseline_sha256):
    config = generation_config(settings)
    config["threshold_experiment"] = {
        "technical_lexical_min_coverage": threshold, "backend_default": 0.34,
        "scope": "hierarchical_technical_binding_only", "baseline_results_sha256": baseline_sha256,
        "script_sha256": file_digest(Path(__file__)),
    }
    return config


def verify_sources(baseline):
    from app.settings import load_settings
    old = baseline["metadata"]["generation_config"]
    current = generation_config(load_settings())
    for name in ("dataset_sha256", "dataset_version", "model", "generator_transport", "native_model_profile", "versions", "retrieval_mode", "retrieval_limit", "runner_sha256"):
        if old[name] != current[name]:
            raise ValueError("Cambió el perfil de la línea base")
    if current["retrieval_mode"] != "lexical":
        raise ValueError("El experimento requiere el modo léxico original")
    differences = [name for name, digest_value in old["source_sha256"].items() if current["source_sha256"][name] != digest_value]
    if differences != ["app/rag/retriever.py"]:
        raise ValueError("Solo se permite exponer el umbral en el recuperador compartido")
    from app.rag.retriever import retrieve_documents
    if inspect.signature(retrieve_documents).parameters["lexical_min_coverage"].default != 0.34:
        raise ValueError("El valor predeterminado cambió")
    return current


def retrieval_comparison(directory, baseline_dir):
    from rag_eval.runtime import prepare_case
    from rag_eval.compare_retrieval import source_hit
    baseline = load_run(baseline_dir)
    verify_sources(baseline)
    original_rows = {r["id"]: r for r in baseline["results"]}
    _, samples, dataset_hash = load_dataset(BASE / "dataset_project.json")
    hashes = baseline_hashes(baseline_dir)
    directory.mkdir(parents=True, exist_ok=True)
    if (directory / "retrieval_comparison.json").exists():
        raise ValueError("La comparación ya existe; usar generate o report para continuar")
    default_contexts = {s["id"]: prepare_case(s) for s in samples}
    if any(default_contexts[s["id"]]["contexts"] != original_rows[s["id"]]["retrieved_contexts"] for s in samples):
        raise ValueError("El recorrido predeterminado no reproduce la línea base")
    configurations = []
    diagnostics = []
    for threshold in THRESHOLDS:
        rows = []
        with technical_threshold(threshold):
            for sample in samples:
                item = prepare_case(sample)
                original = original_rows[sample["id"]]
                old_ids = original["source_ids"]
                new_ids = item["source_ids"]
                old_contexts = original["retrieved_contexts"]
                rows.append({"id": sample["id"], "route": sample["route"], "answerable": sample["answerable"],
                             "source_ids": new_ids, "contexts": item["contexts"], "context": item["context"],
                             "source_hit": source_hit(sample, item), "changed": old_contexts != item["contexts"],
                             "old_source_ids": old_ids, "source_order_changed": old_ids != [x for x in new_ids if x in old_ids],
                             "newly_retrieved": not old_contexts and bool(item["contexts"]),
                             "lost_expected_source": sample["answerable"] and sample["route"] == "technical" and sample["expected_source_id"] in old_ids and sample["expected_source_id"] not in new_ids})
        technical = [r for r in rows if r["route"] == "technical" and r["answerable"]]
        old_working = [r for r in technical if original_rows[r["id"]]["retrieved_contexts"]]
        controls = [r for r in rows if not r["answerable"] and r["route"] == "technical"]
        summary = {"threshold": threshold, "technical_with_context": sum(bool(r["contexts"]) for r in technical),
                   "technical_total": len(technical), "technical_expected_source_hits": sum(r["source_hit"] is True for r in technical),
                   "new_technical_ids": [r["id"] for r in technical if r["newly_retrieved"]],
                   "changed_old_technical_ids": [r["id"] for r in old_working if r["changed"]],
                   "source_order_changed_old_ids": [r["id"] for r in old_working if r["source_order_changed"]],
                   "expected_source_regressions": [r["id"] for r in rows if r["lost_expected_source"]],
                   "technical_control_false_positives": [r["id"] for r in controls if r["contexts"]],
                   "technical_control_total": len(controls),
                   "faq_changed_ids": [r["id"] for r in rows if r["route"] == "faq" and r["changed"]],
                   "all_changed_ids": [r["id"] for r in rows if r["changed"]]}
        configurations.append({"summary": summary, "results": rows})
    from app.agents.jerarquico.retriever import load_knowledge_documents
    documents = {d.id:d for d in load_knowledge_documents()}
    for sample in samples:
        if sample["id"] not in FAILED_IDS:
            continue
        observations = []
        with technical_threshold(0.34, observations):
            prepare_case(sample)
        candidate = next(c for c in observations[0]["candidates"] if c["source_id"].endswith("#"+sample["expected_source_id"]))
        document = documents[sample["expected_source_id"]]
        supported = document.diagnosis in sample["reference"] and document.solution in sample["reference"]
        if not supported or not all(candidate["filters"].values()):
            raise ValueError("No se verificó la referencia esperada")
        diagnostics.append({"id": sample["id"], "expected_source_id": sample["expected_source_id"],
                            "candidate": candidate, "diagnosis": document.diagnosis, "solution": document.solution,
                            "reference_contains_diagnosis_and_solution": supported,
                            "acceptance": {str(t): candidate["coverage"] >= t for t in THRESHOLDS}})
    eligible = [c["summary"] for c in configurations if c["summary"]["technical_with_context"] > 17
                and not c["summary"]["expected_source_regressions"] and not c["summary"]["technical_control_false_positives"]
                and not c["summary"]["faq_changed_ids"]]
    selected = max(eligible, key=lambda x:(x["technical_expected_source_hits"], x["technical_with_context"], -len(x["changed_old_technical_ids"]), x["threshold"])) if eligible else None
    payload = {"baseline_dir": baseline_dir.relative_to(ROOT).as_posix(), "baseline_results_sha256": file_digest(baseline_dir / "results.json"),
               "baseline_files_sha256": hashes, "dataset_sha256": dataset_hash, "source_sha256": source_manifest(),
               "script_sha256": file_digest(Path(__file__)), "default_reproduces_baseline_all_30": True,
               "comparator": "coverage >= lexical_min_coverage (sin redondear)",
               "faq_control_scope": "control_sports usa FAQ; no prueba el umbral técnico",
               "technical_control_scope": "control_recipe; un único negativo sintético",
               "selected_threshold": selected["threshold"] if selected else None,
               "configurations": configurations, "diagnostics": diagnostics}
    write_json(directory / "retrieval_comparison.json", payload)
    write_json(directory / "diagnostics.json", diagnostics)
    assert_baseline_unchanged(baseline_dir, hashes)
    report(directory)
    print(json.dumps([c["summary"] for c in configurations], ensure_ascii=True, indent=2))
    print("Umbral seleccionado:", payload["selected_threshold"])
    return 0


def prepare_candidate(directory):
    from app.settings import load_settings
    from rag_eval.runtime import prepare_case
    from rag_eval.baseline_report import save_baseline
    comparison = read_json(directory / "retrieval_comparison.json")
    if comparison["script_sha256"] != file_digest(Path(__file__)):
        raise ValueError("Cambió el script del experimento; usar otra corrida")
    baseline_dir = ROOT / comparison["baseline_dir"]
    assert_baseline_unchanged(baseline_dir, comparison["baseline_files_sha256"])
    baseline = load_run(baseline_dir)
    verify_sources(baseline)
    threshold = comparison["selected_threshold"]
    if threshold is None:
        raise ValueError("No hay candidato elegible")
    target = directory / "candidate"
    config = experiment_config(load_settings(), threshold, comparison["baseline_results_sha256"])
    if (target / "results.json").exists():
        return target, load_run(target, config)
    old = {r["id"]: r for r in baseline["results"]}
    _, samples, _ = load_dataset(BASE / "dataset_project.json")
    rows = []
    changed_ids = []
    with technical_threshold(threshold):
        for sample in samples:
            prepared = prepare_case(sample)
            previous = old[sample["id"]]
            if previous["retrieved_contexts"] == prepared["contexts"]:
                row = deepcopy(previous)
                row["experiment_reuse"] = {"run": comparison["baseline_dir"], "reason": "identical_ordered_context_and_generation_profile"}
            else:
                row = new_case(sample, prepared)
                changed_ids.append(sample["id"])
            rows.append(row)
    payload = new_run(config, rows, baseline["metadata"]["judge_model"])
    payload["metadata"].update(scoring_profiles=deepcopy(baseline["metadata"]["scoring_profiles"]),
                               scope_note=f"Experimento técnico con umbral {threshold}; FAQ sin cambios; solo se generan contextos cambiados.",
                               changed_context_ids=changed_ids, baseline_dir=comparison["baseline_dir"],
                               baseline_results_sha256=comparison["baseline_results_sha256"])
    save_baseline(target, payload)
    return target, payload


def generate_candidate(directory):
    from rag_eval import baseline
    target, payload = prepare_candidate(directory)
    experiment = payload["metadata"]["generation_config"]["threshold_experiment"]
    threshold = experiment["technical_lexical_min_coverage"]
    args = SimpleNamespace(run=target, judge_model=payload["metadata"]["judge_model"], reuse_run=None,
                           only=payload["metadata"]["changed_context_ids"], limit=0, prepare_only=False)
    if not args.only:
        return 0
    def scoped_config(settings):
        return experiment_config(settings, threshold, experiment["baseline_results_sha256"])
    with technical_threshold(threshold), patch.object(baseline, "generation_config", scoped_config):
        result = baseline.generate(args)
    comparison = read_json(directory / "retrieval_comparison.json")
    assert_baseline_unchanged(ROOT / comparison["baseline_dir"], comparison["baseline_files_sha256"])
    return result


def paired_metrics(baseline_rows, candidate_rows, identifiers):
    from rag_eval.baseline_report import metric_value
    from rag_eval.text_metrics import corpus_bleu
    result = {}
    for metric in (*RAGAS_METRICS, "rouge1", "rouge2", "rougeL"):
        ids = [i for i in identifiers if metric_value(baseline_rows[i],metric) is not None and metric_value(candidate_rows[i],metric) is not None]
        left = [metric_value(baseline_rows[i],metric) for i in ids]
        right = [metric_value(candidate_rows[i],metric) for i in ids]
        result[metric] = {"n":len(ids),"baseline":mean(left) if ids else None,"candidate":mean(right) if ids else None,
                          "mean_paired_delta":mean([b-a for a,b in zip(left,right)]) if ids else None}
    result["bleu_corpus"] = {"baseline":corpus_bleu([baseline_rows[i] for i in identifiers]),
                             "candidate":corpus_bleu([candidate_rows[i] for i in identifiers])}
    return result


def report(directory):
    comparison = read_json(directory / "retrieval_comparison.json")
    lines = ["# Comparación experimental del umbral técnico", "", "El backend conserva 0.34 por defecto. Se modifica solo la llamada del adaptador técnico; la FAQ no recibe el umbral experimental.", "",
             "| Umbral | Cobertura técnica | Fuentes esperadas | Nuevos casos | Cambios en 17 previos | Regresiones fuente | Falsos positivos control técnico |",
             "| ---: | ---: | ---: | --- | ---: | ---: | ---: |"]
    for config in comparison["configurations"]:
        s=config["summary"]
        lines.append(f"| {s['threshold']:.2f} | {s['technical_with_context']}/20 | {s['technical_expected_source_hits']}/20 | {', '.join(s['new_technical_ids']) or 'ninguno'} | {len(s['changed_old_technical_ids'])} | {len(s['expected_source_regressions'])} | {len(s['technical_control_false_positives'])}/{s['technical_control_total']} |")
    lines += ["", f"Candidato seleccionado: {comparison['selected_threshold']}. Se priorizan fuente esperada/cobertura, menos cambios en los casos previos y el umbral más alto en caso de empate.",
              "El control FAQ control_sports no está expuesto a este cambio. El control técnico es solo control_recipe; un negativo no permite estimar generalización.", "",
              "Los valores fueron elegidos a partir de estos fallos. La comparación usa datos de ajuste, no un conjunto independiente. Validar preguntas nuevas antes de adoptar el umbral."]
    target=directory/"candidate"
    if (target/"results.json").exists():
        from rag_eval.baseline_report import metric_value, summarize_group
        baseline=load_run(ROOT/comparison["baseline_dir"])
        candidate=load_run(target)
        left={r["id"]:r for r in baseline["results"]}
        right={r["id"]:r for r in candidate["results"]}
        common=[i for i in left if left[i]["answerable"] and left[i].get("response") and right[i].get("response")]
        changed_common=[i for i in common if i in candidate["metadata"]["changed_context_ids"]]
        new_ids=[i for i in right if right[i]["answerable"] and not left[i]["retrieved_contexts"] and right[i]["retrieved_contexts"]]
        details={"common_answerable_ids":common,"changed_common_ids":changed_common,"newly_retrieved_ids":new_ids,
                 "common_answerable":paired_metrics(left,right,common),
                 "common_technical":paired_metrics(left,right,[i for i in common if left[i]["route"]=="technical"]),
                 "changed_common":paired_metrics(left,right,changed_common),
                 "changed_common_per_id":{i:{m:{"baseline":metric_value(left[i],m),"candidate":metric_value(right[i],m)} for m in (*RAGAS_METRICS,"rouge1","rouge2","rougeL")} for i in changed_common},
                 "newly_retrieved":summarize_group([right[i] for i in new_ids],True),
                 "newly_retrieved_per_id":{i:{m:metric_value(right[i],m) for m in (*RAGAS_METRICS,"rouge1","rouge2","rougeL")} for i in new_ids},
                 "controls":[{"id":r["id"],"context_count":len(r["retrieved_contexts"]),"response_relevancy":metric_value(r,"response_relevancy"),"abstention":r["abstention"]} for r in right.values() if not r["answerable"]]}
        write_json(directory/"metrics_comparison.json",details)
        lines += ["", "## Métricas sobre IDs contestables comunes", "", "Response Relevancy excluye ambos controles. Los controles se reportan aparte en metrics_comparison.json.", "",
                  "| Métrica | N pareado | Línea base | Candidato | Delta medio |", "| --- | ---: | ---: | ---: | ---: |"]
        for metric,s in details["common_answerable"].items():
            if metric=="bleu_corpus": continue
            fmt=lambda x:f"{x:.4f}" if x is not None else "pendiente"
            lines.append(f"| {metric} | {s['n']} | {fmt(s['baseline'])} | {fmt(s['candidate'])} | {fmt(s['mean_paired_delta'])} |")
        lines += ["", "## Casos recuperados por primera vez", "", "No tienen puntuación de respuesta de línea base; se presentan aparte, sin atribuir un delta inventado.", "",
                  "| ID | Precisión | Recall | Fidelidad | Relevancia | Factual F1 |", "| --- | ---: | ---: | ---: | ---: | ---: |"]
        for i in new_ids:
            vals=[metric_value(right[i],m) for m in RAGAS_METRICS]
            lines.append("| "+i+" | "+" | ".join(f"{v:.4f}" if v is not None else "pendiente" for v in vals)+" |")
    (directory/"comparison.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    assert_baseline_unchanged(ROOT/comparison["baseline_dir"],comparison["baseline_files_sha256"])
    return 0


def main():
    isolate_process()
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action",choices=("retrieve","generate","report"))
    parser.add_argument("--run",type=Path,required=True)
    parser.add_argument("--baseline",type=Path,default=ROOT/".local/ragas/baseline-v1-final")
    args=parser.parse_args()
    directory=local_directory(args.run)
    if args.action=="retrieve":return retrieval_comparison(directory,local_directory(args.baseline))
    if args.action=="generate":return generate_candidate(directory)
    return report(directory)


if __name__=="__main__":
    try: raise SystemExit(main())
    except Exception as error:
        print("Experimento detenido. Tipo:",type(error).__name__)
        raise SystemExit(1)
