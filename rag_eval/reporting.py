"""Informes reproducibles: puntuaciones válidas y cobertura siempre separadas."""
import csv
import json
import math
from pathlib import Path
from statistics import mean, pstdev

METRICS = ("faithfulness", "context_precision", "context_recall")
OPERATIONAL_ERRORS = {"preparation_error", "generation_error", "metric_error", "quota_exhausted"}


def summarize(rows, planned):
    metrics = {}
    for name in METRICS:
        values = [r[name] for r in rows if isinstance(r.get(name), (int, float)) and not isinstance(r[name], bool) and math.isfinite(r[name])]
        metrics[name] = {"mean": mean(values) if values else None, "std_population": pstdev(values) if values else None, "evaluated": len(values)}
    positives = [r for r in rows if r["answerable"]]
    negatives = [r for r in rows if not r["answerable"]]
    return {
        "planned": planned, "processed": len(rows),
        "operational_errors": sum(r["status"] in OPERATIONAL_ERRORS for r in rows),
        "answerable": len(positives), "answerable_with_context": sum(bool(r.get("context_count")) for r in positives),
        "controls": len(negatives), "controls_without_context": sum(r.get("context_count") == 0 for r in negatives),
        "status_counts": {s: sum(r["status"] == s for r in rows) for s in sorted({r["status"] for r in rows})},
        "metrics": metrics,
    }


def save_report(directory, rows, metadata):
    directory = Path(directory)
    summary = summarize(rows, metadata["planned_cases"])
    payload = {"metadata": metadata, "summary": summary, "results": rows}
    target = directory / "results.json"
    temporary = directory / "results.tmp"
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    temporary.replace(target)
    fields = ["id", "route", "answerable", "status", "context_count", "expected_source_hit", *METRICS, "failed_metrics"]
    with (directory / "results.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({**row, "failed_metrics": json.dumps(row.get("failed_metrics", []), ensure_ascii=False)})
    lines = ["# Evaluación Ragas de componentes TechFixAI", "", "Alcance: diagnóstico técnico jerárquico y FAQ compartida; no es una prueba HTTP ni de todos los patrones.", "",
             f"Casos procesados: {summary['processed']}/{summary['planned']}. Errores operativos: {summary['operational_errors']}.",
             f"Preguntas contestables con contexto: {summary['answerable_with_context']}/{summary['answerable']}.",
             f"Controles sin contexto: {summary['controls_without_context']}/{summary['controls']}.", "",
             "| Métrica | Media | Desviación poblacional | Casos válidos |", "| --- | ---: | ---: | ---: |"]
    for name, values in summary["metrics"].items():
        avg = f"{values['mean']:.3f}" if values["mean"] is not None else "—"
        std = f"{values['std_population']:.3f}" if values["std_population"] is not None else "—"
        lines.append(f"| {name} | {avg} | {std} | {values['evaluated']} |")
    lines += ["", "| Caso | Ruta | Estado | Contextos | Fidelidad | Precisión | Cobertura |", "| --- | --- | --- | ---: | ---: | ---: | ---: |"]
    for row in rows:
        scores = [f"{row[name]:.3f}" if row.get(name) is not None else "—" for name in METRICS]
        lines.append(f"| {row['id']} | {row['route']} | {row['status']} | {row.get('context_count', 0)} | " + " | ".join(scores) + " |")
    lines += ["", "Los casos sin contexto no reciben puntuaciones inventadas y no entran en las medias. Revisar siempre denominadores y estados.",
              "El mismo modelo genera y evalúa." if metadata.get("same_model_for_generation_and_judging") else "Generador y juez están identificados por separado en los metadatos.",
              "Las referencias se verificaron contra el corpus por código; no hubo revisión humana independiente.",
              "La FAQ se declara demostrativa en la fuente: estas puntuaciones miden fidelidad al corpus, no veracidad comercial.",
              "La versión anterior usaba un prompt de prueba y no es una comparación controlada con estos componentes."]
    lines += ["", f"Modelo generador: {metadata.get('model', 'no registrado')}. Modelo juez: {metadata.get('judge_model', 'no registrado')}.", f"Modelo configurado en el backend: {metadata.get('configured_backend_model', 'no registrado')}. Coincide con el generador evaluado: {metadata.get('model_matches_backend', False)}."]
    (directory / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return summary