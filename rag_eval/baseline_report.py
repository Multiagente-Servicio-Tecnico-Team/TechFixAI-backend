"""Reportes de cobertura por métrica y categoría, sin confundir ausentes con ceros."""
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
from statistics import mean, pstdev

from rag_eval.baseline_state import RAGAS_METRICS, metric_eligibility, now
from rag_eval.text_metrics import ROUGE_TYPES, corpus_bleu


def metric_value(row, name):
    if name in ROUGE_TYPES:
        return row.get("metrics", {}).get("text", {}).get("rouge", {}).get(name, {}).get("f1")
    result = row.get("metrics", {}).get(name, {})
    return result.get("value") if result.get("status") == "ok" else None


def summarize_group(rows, include_text):
    metrics = {}
    for name in (*RAGAS_METRICS, *ROUGE_TYPES):
        values = [metric_value(row, name) for row in rows if metric_value(row, name) is not None]
        eligible = sum(metric_eligibility("text" if name in ROUGE_TYPES else name, row) == ("pending", None) for row in rows)
        metrics[name] = {"mean": mean(values) if values else None,
                         "std_population": pstdev(values) if values else None,
                         "evaluated": len(values), "available_inputs": eligible, "total_cases": len(rows)}
    answerable = [r for r in rows if r["answerable"]]
    controls = [r for r in rows if not r["answerable"]]
    return {"cases": len(rows), "answerable": len(answerable),
            "answerable_with_context": sum(bool(r["retrieved_contexts"]) for r in answerable),
            "responses": sum(bool(r.get("response")) for r in rows),
            "generation_statuses": dict(Counter(r["generation_status"] for r in rows)),
            "retrieval_statuses": dict(Counter(r["retrieval_status"] for r in rows)),
            "controls": len(controls), "controls_without_context": sum(not r["retrieved_contexts"] for r in controls),
            "observed_abstentions": sum(r.get("abstention", {}).get("observed") is True for r in controls if r.get("abstention")),
            "controls_without_observable_response": sum(not r.get("response") for r in controls),
            "generation_errors": sum(r["generation_status"] == "api_error" for r in rows),
            "metric_statuses": {name: dict(Counter(r.get("metrics", {}).get(name, {}).get("status", "pending") for r in rows)) for name in (*RAGAS_METRICS, "text")},
            "metrics": metrics, "bleu_corpus": corpus_bleu([r for r in rows if r.get("metrics", {}).get("text", {}).get("status") == "ok"]) if include_text else None}


def save_baseline(directory, payload):
    directory.mkdir(parents=True, exist_ok=True)
    rows = payload["results"]
    for row in rows:
        for name in (*RAGAS_METRICS, "text"):
            status, reason = metric_eligibility(name, row)
            old = row["metrics"].get(name, {})
            if old.get("status") not in {"ok", "error", "quota_pending", "dependency_pending", "cache_miss"}:
                row["metrics"][name] = {"status": status, "reason": reason}
    include_text = "text" in payload["metadata"]["scoring_profiles"]
    payload["summary"] = {group: summarize_group(selected, include_text) for group, selected in {
        "all": rows, "technical": [r for r in rows if r["category"] == "technical"],
        "faq": [r for r in rows if r["category"] == "faq"],
        "out_of_corpus": [r for r in rows if r["category"] == "out_of_corpus"],
    }.items()}
    payload["metadata"]["updated_at_utc"] = now()
    payload["metadata"]["reporter_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    temporary = directory / "results.tmp"
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    temporary.replace(directory / "results.json")
    fields = ["id", "category", "user_input", "reference", "reference_source", "response", "retrieval_status", "context_count",
              "generation_status", "generator_invoked", "abstention_observed", "errors"]
    for name in RAGAS_METRICS:
        fields += [name, name + "_status", name + "_reason"]
    for name in ROUGE_TYPES:
        fields += [name + "_precision", name + "_recall", name + "_f1"]
    fields += ["text_status", "text_reason"]
    with (directory / "results.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            metric_errors = [{"stage": "metric", "metric": name,
                              **{key: result[key] for key in ("error_type", "http_status", "code", "quota") if key in result}}
                             for name, result in row["metrics"].items() if "error_type" in result]
            output = {**row, "context_count": len(row["retrieved_contexts"]),
                      "abstention_observed": (row.get("abstention") or {}).get("observed"),
                      "errors": json.dumps(row["errors"] + metric_errors, ensure_ascii=False)}
            for name in RAGAS_METRICS:
                result = row["metrics"][name]
                output.update({name: metric_value(row, name), name + "_status": result["status"], name + "_reason": result.get("reason")})
            text = row["metrics"]["text"]
            for name, score in text.get("rouge", {}).items():
                output.update({name + "_" + key: value for key, value in score.items()})
            output.update(text_status=text["status"], text_reason=text.get("reason"))
            writer.writerow(output)
    (directory / "summary.json").write_text(json.dumps(payload["summary"], ensure_ascii=False, indent=2), encoding="utf-8")
    config = payload["metadata"]["generation_config"]
    lines = ["# Línea base automática del RAG", "", payload["metadata"]["scope_note"], "",
             f"Generador: {config['model']}; juez previsto: {payload['metadata']['judge_model']}.",
             f"Dataset v{config['dataset_version']}; SHA256: {config['dataset_sha256']}.",
             "Referencias extraídas del corpus, verificadas por código; sin revisión humana independiente. FAQ demostrativa.",
             "BLEU y ROUGE miden coincidencia textual, no exactitud factual. BLEU usa escala 0–100; las demás 0–1.",
             "Las medias solo incluyen casos puntuados; revisar cobertura, ausencias y estados por ID.", ""]
    for group, summary in payload["summary"].items():
        lines += [f"## {group}", "", f"Casos: {summary['cases']}; respuestas: {summary['responses']}; contexto en contestables: {summary['answerable_with_context']}/{summary['answerable']}.",
                  f"Estados de generación: {summary['generation_statuses']}.", "",
                  "| Grupo | Métrica | Resultado | Casos válidos | Entradas disponibles |", "| --- | --- | ---: | ---: | ---: |"]
        for name, score in summary["metrics"].items():
            family = "recuperación" if name in {"context_precision", "context_recall"} else "texto" if name in ROUGE_TYPES else "respuesta"
            value = f"{score['mean']:.4f}" if score["mean"] is not None else "pendiente / no aplicable"
            lines.append(f"| {family} | {name} | {value} | {score['evaluated']} | {score['available_inputs']} |")
        if summary["bleu_corpus"]:
            for name, score in summary["bleu_corpus"].items():
                value = f"{score['value']:.4f}" if score["value"] is not None else "no aplicable"
                lines.append(f"| texto (corpus) | {name} | {value} | {score['evaluated']} | {score['evaluated']} |")
        if summary["controls"]:
            lines += ["", f"Controles sin contexto: {summary['controls_without_context']}/{summary['controls']}; abstenciones observadas: {summary['observed_abstentions']}; sin respuesta observable: {summary['controls_without_observable_response']}."]
        lines += ["", f"Errores de generación: {summary['generation_errors']}.", "",
                  "| Métrica | Estados y cantidad de casos |", "| --- | --- |"]
        lines += [f"| {name} | {states} |" for name, states in summary["metric_statuses"].items()]
        lines.append("")
    lines += ["## Estado por ID", "", "| ID | Categoría | Contextos | Generación |", "| --- | --- | ---: | --- |"]
    lines += [f"| {r['id']} | {r['category']} | {len(r['retrieved_contexts'])} | {r['generation_status']} |" for r in rows]
    lines += ["", "No recuperar contexto no demuestra por sí solo que se emitió una abstención. El componente técnico no se invoca sin contexto en este evaluador.",
              "Los errores se guardan como clase/HTTP/código permitido, sin textos de excepciones ni credenciales.", ""]
    (directory / "report.md").write_text("\n".join(lines), encoding="utf-8")
    return payload["summary"]
