"""Evaluación reproducible de los componentes RAG reales con métricas Ragas."""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BASE = Path(__file__).resolve().parent


def isolate_process():
    # Solo este proceso: evitar escrituras y trazas remotas al importar componentes.
    os.environ["DATABASE_URL"] = ""
    for name in ("LANGSMITH_TRACING", "LANGCHAIN_TRACING", "LANGCHAIN_TRACING_V2"):
        os.environ[name] = "false"
    os.environ["RAGAS_DO_NOT_TRACK"] = "true"


def load_dataset(path):
    raw = path.read_bytes()
    dataset = json.loads(raw)
    rows = dataset["rows"]
    identifiers = set()
    for row in rows:
        if row["id"] in identifiers or row["route"] not in {"technical", "faq"}:
            raise ValueError("Identificador duplicado o ruta no admitida")
        identifiers.add(row["id"])
        if not row["user_input"].strip() or not isinstance(row["answerable"], bool):
            raise ValueError("Consulta o etiqueta inválida")
        if row["answerable"]:
            source = (ROOT / row["reference_source"]).resolve()
            if not source.is_relative_to(ROOT):
                raise ValueError("Fuente fuera del proyecto")
            text = source.read_text(encoding="utf-8")
            excerpt = row["reference_excerpt"]
            if ' '.join(row["reference"].split()) != ' '.join(excerpt.split()):
                raise ValueError("La referencia no coincide con el extracto verificado")
            if row["reference_anchor"] not in text or not all(line in text for line in excerpt.splitlines()):
                raise ValueError("Referencia no encontrada en su fuente")
            if hashlib.sha256(excerpt.encode()).hexdigest() != row["reference_sha256"] or not row["reference"].strip():
                raise ValueError("Referencia alterada o vacía")
    return dataset, rows, hashlib.sha256(raw).hexdigest()


def source_manifest():
    names = ["app/adapters/llm/model_factory.py", "app/rag/retriever.py", "app/rag/ingest.py", "app/rag/sources.py", "app/rag/faq.py", "app/agents/jerarquico/retriever.py", "app/agents/jerarquico/technical_support.py", "app/agents/jerarquico/knowledge_retrieval.py", "app/agents/jerarquico/schemas.py", "rag_eval/native_provider.py", "rag_eval/providers.py", "rag_eval/metrics.py", "rag_eval/runtime.py", "rag_eval/evaluate_project.py", "rag_eval/reporting.py"]
    names += [p.relative_to(ROOT).as_posix() for p in (ROOT / "app/agents/jerarquico/knowledge_base").glob("*.md")]
    return {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in sorted(names)}


async def main():
    isolate_process()
    from openai import AsyncOpenAI
    from rag_eval.metrics import create_metrics
    from app.settings import load_settings
    from rag_eval.providers import ENDPOINT, CompletionStore, ProjectModel, StrictGroqJudge, cache_key, safe_error, daily_quota
    from rag_eval.reporting import METRICS, OPERATIONAL_ERRORS, save_report
    from rag_eval.runtime import generate_case, prepare_case

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--only", nargs="+", help="Identificadores específicos; no modifica sus preguntas.")
    parser.add_argument("--resume", type=Path, help="Directorio de una corrida compatible para reanudar errores.")
    parser.add_argument("--model", help="Modelo generador solo para esta evaluación; no modifica el backend.")
    parser.add_argument("--judge-model", help="Modelo juez; por defecto usa el modelo generador.")
    parser.add_argument("--generator-transport", choices=("bridge", "backend"), default="bridge", help="backend reutiliza la fábrica ChatGroq del proyecto.")
    args = parser.parse_args()
    if args.limit < 0:
        parser.error("--limit no puede ser negativo")
    dataset, samples, dataset_hash = load_dataset(BASE / "dataset_project.json")
    if args.only:
        if set(args.only) - {r["id"] for r in samples}:
            parser.error("Hay identificadores desconocidos")
        samples = [r for r in samples if r["id"] in args.only]
    if args.limit:
        samples = samples[:args.limit]
    settings = load_settings()
    prepared = {}
    for sample in samples:
        item = prepare_case(sample)
        if "\n\n".join(item["contexts"]) != item["context"]:
            raise ValueError("Los contextos no reproducen la entrada real al generador")
        prepared[sample["id"]] = item
        print(f"{sample['id']}: {len(item['contexts'])} contextos ({sample['route']})", flush=True)
    if args.dry_run:
        print(f"{len(samples)} casos verificados con referencias de fuente. No se llamó a Groq.")
        return 0
    if not settings.groq_api_key or not settings.groq_model:
        raise ValueError("Falta configurar Groq")
    generator_model = args.model or settings.groq_model
    judge_model = args.judge_model or generator_model
    backend_profile = None
    if args.generator_transport == "backend":
        if generator_model != settings.groq_model:
            parser.error("El transporte backend requiere el modelo configurado en el proyecto")
        from rag_eval.native_provider import native_profile
        backend_profile = native_profile(settings)
    version_names = ("ragas", "openai", "pydantic", "pyarrow", "datasets", "langchain-community")
    config = {"scope": "production_rag_components_not_http_chat", "dataset_sha256": dataset_hash, "source_sha256": source_manifest(), "model": generator_model, "judge_model": judge_model, "configured_backend_model": settings.groq_model, "model_matches_backend": generator_model == settings.groq_model, "temperature": 0, "reasoning_effort": "low", "max_completion_tokens": 4096, "judge_format": "json_schema_strict", "metric_prompt_profile": "ragas_original_instructions_without_few_shot_examples", "technical_generation_format": "json_object_as_requested_by_project", "retrieval_mode": settings.rag_retrieval_mode, "retrieval_limit": 3, "case_ids": [s["id"] for s in samples], "versions": {n: importlib.metadata.version(n) for n in version_names}}
    config.update(generator_transport=args.generator_transport, native_model_profile=backend_profile, judge_reasoning_effort="low", judge_max_completion_tokens=4096)
    if args.generator_transport == "backend":
        config.update(reasoning_effort="backend_default", max_completion_tokens=None)
    fingerprint = cache_key(config)
    output_root = ROOT / ".local" / "ragas"
    if args.resume:
        output = args.resume.resolve()
        if not output.is_relative_to(output_root.resolve()):
            parser.error("--resume debe estar dentro de .local/ragas")
        previous = json.loads((output / "results.json").read_text(encoding="utf-8"))
        if previous["metadata"]["fingerprint"] != fingerprint:
            parser.error("La configuración o las fuentes cambiaron: crea una corrida nueva")
        metadata = previous["metadata"]
        existing = {r["id"]: r for r in previous["results"]}
    else:
        output = output_root / ("project-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
        output.mkdir(parents=True, exist_ok=False)
        revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
        metadata = {**config, "fingerprint": fingerprint, "git_commit": revision, "planned_cases": len(samples), "reference_review": dataset["reference_review"], "faq_notice": dataset["faq_notice"], "started_at_utc": datetime.now(timezone.utc).isoformat(), "provider_transport": "native_backend_factory" if args.generator_transport == "backend" else "evaluation_bridge_calls_production_component_functions", "same_model_for_generation_and_judging": generator_model == judge_model}
        existing = {}
    rows = [existing[s["id"]] for s in samples if s["id"] in existing]
    save_report(output, rows, metadata)
    print(f"Directorio de evidencia: {output}", flush=True)
    store = CompletionStore(output_root / "cache-v2")
    if args.generator_transport == "backend":
        from rag_eval.native_provider import create_native_model
        generator = create_native_model(settings, store)
    else:
        generator = ProjectModel(settings.groq_api_key, generator_model, store)
    async with AsyncOpenAI(api_key=settings.groq_api_key, base_url=ENDPOINT, timeout=60, max_retries=0) as client:
        judge = StrictGroqJudge(client, judge_model, store)
        scorers = create_metrics(judge)
        for sample in samples:
            old = existing.get(sample["id"])
            if old and old["status"] not in OPERATIONAL_ERRORS:
                print(f"{sample['id']}: ya completado", flush=True)
                continue
            item = prepared[sample["id"]]
            row = {**sample, "context_count": len(item["contexts"]), "retrieved_contexts": item["contexts"], "context_sent_to_generator": item["context"], "source_ids": item["source_ids"], "response": old.get("response") if old else None, "diagnosis": old.get("diagnosis") if old else None, "status": "ok", "failed_metrics": [], **{name: old.get(name) if old else None for name in METRICS}}
            row["expected_source_hit"] = sample.get("expected_source_id") in item["source_ids"] if sample["route"] == "technical" and sample["answerable"] else sample.get("reference_anchor", "") in item["context"] if sample["answerable"] else None
            if not item["contexts"]:
                row["status"] = "no_context" if sample["answerable"] else "expected_abstention"
                if sample["route"] == "faq":
                    row["response"], row["diagnosis"] = generate_case(sample, item, generator)
            else:
                if not row["response"]:
                    try:
                        print(f"{sample['id']}: generación del componente real", flush=True)
                        row["response"], row["diagnosis"] = await asyncio.to_thread(generate_case, sample, item, generator)
                    except Exception as error:
                        row.update(status="quota_exhausted" if daily_quota(error) else "generation_error", generation_error=safe_error(error))
                if not sample["answerable"]:
                    row["status"] = "unexpected_context"
                elif row["status"] != "quota_exhausted":
                    for name, scorer in scorers.items():
                        if row[name] is not None or (name == "faithfulness" and not row["response"]):
                            continue
                        print(f"{sample['id']}: {name}", flush=True)
                        arguments = {"user_input": sample["user_input"], "retrieved_contexts": item["contexts"]}
                        arguments.update({"response": row["response"]} if name == "faithfulness" else {"reference": sample["reference"]})
                        try:
                            score = float((await scorer.ascore(**arguments)).value)
                            if not math.isfinite(score) or not 0 <= score <= 1:
                                raise ValueError("Puntuación inválida")
                            row[name] = score
                        except Exception as error:
                            row["failed_metrics"].append({"metric": name, **safe_error(error)})
                            if daily_quota(error):
                                row["status"] = "quota_exhausted"
                                break
                    if row["failed_metrics"]:
                        row["status"] = "metric_error" if row["status"] == "ok" else row["status"]
            existing[sample["id"]] = row
            rows = [existing[s["id"]] for s in samples if s["id"] in existing]
            metadata["provider_calls"] = store.calls
            metadata["cache_hits"] = store.hits
            summary = save_report(output, rows, metadata)
            print(f"{sample['id']}: {row['status']} | " + " | ".join(f"{n}={row[n]}" for n in METRICS), flush=True)
            if row["status"] == "quota_exhausted":
                metadata["stop_reason"] = "daily_quota_exhausted"
                save_report(output, rows, metadata)
                print(f"Cuota diaria agotada. Evidencia guardada: {output}. Reanuda después con la misma configuración.", flush=True)
                return 2
    metadata["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
    summary = save_report(output, rows, metadata)
    print(json.dumps(summary, ensure_ascii=True, indent=2))
    print(f"Evidencia: {output}")
    return 1 if summary["operational_errors"] else 0


if __name__ == "__main__":
    isolate_process()
    from rag_eval.providers import safe_error
    try:
        raise SystemExit(asyncio.run(main()))
    except Exception as error:
        print("Evaluación detenida:", safe_error(error))
        raise SystemExit(1)