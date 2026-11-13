"""Generar, reanudar y puntuar la línea base del RAG sin modificar app/."""
from __future__ import annotations

import argparse
import asyncio
import json
import math
from pathlib import Path
from types import SimpleNamespace

from rag_eval.baseline_state import (
    BASE, ROOT, RAGAS_METRICS, digest, file_digest, generation_config, load_dataset,
    load_run, local_directory, merge_historical, metric_eligibility, new_case,
    new_run, now, select_cases, versions,
)
from rag_eval.evaluate_project import isolate_process

DEFAULT_EMBEDDINGS = ROOT / ".local/ragas/embeddings/multilingual-minilm"


class CacheMissError(RuntimeError):
    pass


class ContextRecordingModel:
    """Verifica el contexto usado por el prompt original sin alterar sus mensajes."""

    def __init__(self, model, prepared_context, observations):
        self.model = model
        self.prepared_context = prepared_context
        self.observations = observations

    def with_structured_output(self, schema, *, method):
        return ContextRecordingModel(self.model.with_structured_output(schema, method=method), self.prepared_context, self.observations)

    def invoke(self, messages):
        expected = ("Guías RAG recuperadas:\n" + self.prepared_context,
                    "Contexto FAQ y su procedencia:\n" + self.prepared_context)
        if not any(message.type == "system" and message.content in expected for message in messages):
            raise ValueError("El prompt no usa el contexto registrado")
        self.observations.update(invoked=True, context=self.prepared_context,
                                 messages_sha256=digest([{"role": m.type, "content": m.content} for m in messages]))
        return self.model.invoke(messages)


def record_abstention(row):
    if row["answerable"]:
        return
    from app.rag.faq import FAQ_ABSTENTION
    response = row.get("response")
    row["abstention"] = {"observed": True if response == FAQ_ABSTENTION else None,
                          "method": "exact_backend_faq_abstention" if response == FAQ_ABSTENTION else
                          "no_response_observed" if not response else "unverified_response",
                          "retrieved_material": bool(row["retrieved_contexts"])}


def audit_history(output):
    from rag_eval.runtime import prepare_case
    from rag_eval.evaluate_project import source_manifest
    _, samples, dataset_hash = load_dataset(BASE / "dataset_project.json")
    prepared = {s["id"]: prepare_case(s) for s in samples}
    entries = []
    for path in sorted((ROOT / ".local/ragas").glob("project-*/results.json")):
        evidence = json.loads(path.read_text(encoding="utf-8"))
        meta = evidence["metadata"]
        by_id = {row["id"]: row for row in evidence["results"]}
        states = []
        for sample in samples:
            old = by_id.get(sample["id"])
            contexts = prepared[sample["id"]]["contexts"]
            states.append({"id": sample["id"], "route": sample["route"], "answerable": sample["answerable"],
                           "historical_status": old["status"] if old else "not_processed",
                           "response_available": bool(old and old.get("response")), "current_context_count": len(contexts),
                           "contexts_match": old.get("retrieved_contexts") == contexts if old else None})
        entries.append({"run": path.parent.relative_to(ROOT).as_posix(), "model": meta["model"],
                        "judge_model": meta["judge_model"], "generator_transport": meta.get("generator_transport"),
                        "dataset_matches": meta["dataset_sha256"] == dataset_hash,
                        "sources_match": meta["source_sha256"] == source_manifest(),
                        "summary": evidence["summary"], "states_by_id": states, "evidence_sha256": file_digest(path)})
    report = {"dataset_sha256": dataset_hash, "dataset_cases": len(samples), "runs": entries, "created_at_utc": now()}
    output = local_directory(output)
    output.mkdir(parents=True, exist_ok=True)
    (output / "historical_inventory.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Inventario: {output / 'historical_inventory.json'}")
    return 0


def generate(args):
    from app.settings import load_settings
    from rag_eval.baseline_report import save_baseline
    from rag_eval.native_provider import create_native_model
    from rag_eval.providers import CompletionStore, daily_quota, safe_error
    from rag_eval.runtime import generate_case, prepare_case

    settings = load_settings()
    config = generation_config(settings)
    directory = local_directory(args.run)
    _, samples, _ = load_dataset(BASE / "dataset_project.json")
    prepared = {sample["id"]: prepare_case(sample) for sample in samples}
    if (directory / "results.json").exists():
        payload = load_run(directory, config)
        if payload["metadata"]["judge_model"] != args.judge_model:
            raise ValueError("No cambies el juez de una corrida existente")
    else:
        if directory.exists() and any(directory.iterdir()):
            raise ValueError("El directorio no está vacío")
        rows = [new_case(sample, prepared[sample["id"]]) for sample in samples]
        payload = new_run(config, rows, args.judge_model)
    rows = payload["results"]
    for row in rows:
        if row["retrieved_contexts"] != prepared[row["id"]]["contexts"]:
            raise ValueError("El recuperador produjo otros fragmentos: crea una corrida nueva")
    for path in args.reuse_run or []:
        path = local_directory(path)
        if any(entry["run"] == path.relative_to(ROOT).as_posix() for entry in payload["metadata"]["historical_imports"]):
            continue
        evidence = json.loads((path / "results.json").read_text(encoding="utf-8"))
        imported = merge_historical(payload, evidence, path.relative_to(ROOT).as_posix())
        print(f"Respuestas históricas verificadas: {len(imported)}")
    for row in rows:
        if not row["retrieved_contexts"] and row["route"] == "technical":
            row["generation_status"] = "no_context" if row["answerable"] else "not_applicable"
        record_abstention(row)
    save_baseline(directory, payload)
    selected = select_cases(rows, args.only, args.limit)
    payload["metadata"]["last_generation_selection"] = [row["id"] for row in selected]
    save_baseline(directory, payload)
    if args.prepare_only:
        print(f"Preparados {len(rows)} casos; no se invocaron proveedores. Evidencia: {directory}")
        return 0
    store = CompletionStore(ROOT / ".local/ragas/cache-v2")
    model = None
    calls_before = store.calls
    payload["metadata"].pop("generation_stop_reason", None)
    for row in selected:
        if row["generation_status"] in {"ok", "no_context", "not_applicable"}:
            print(f"{row['id']}: conservado ({row['generation_status']})", flush=True)
            continue
        observations = {}
        try:
            if prepared[row["id"]]["contexts"] and model is None:
                if not settings.groq_api_key:
                    raise ValueError("Falta configurar Groq")
                model = create_native_model(settings, store)
            recording = ContextRecordingModel(model, prepared[row["id"]]["context"], observations)
            response, diagnosis = generate_case(row, prepared[row["id"]], recording)
            if not isinstance(response, str) or not response.strip():
                raise ValueError("Respuesta vacía")
            row.update(response=response, diagnosis=diagnosis, generation_status="ok", generation_evidence={"run": directory.relative_to(ROOT).as_posix()})
            row["errors"] = [e for e in row["errors"] if e["stage"] != "generation"]
        except Exception as error:
            row["generation_status"] = "quota_pending" if daily_quota(error) else "api_error"
            row["errors"] = [e for e in row["errors"] if e["stage"] != "generation"]
            row["errors"].append({"stage": "generation", **safe_error(error)})
            if daily_quota(error):
                payload["metadata"]["generation_stop_reason"] = "daily_quota"
        row.update(generator_invoked=observations.get("invoked", False),
                   context_sent_to_generator=observations.get("context"),
                   prompt_messages_sha256=observations.get("messages_sha256"))
        record_abstention(row)
        payload["metadata"]["generation_calls_last_command"] = store.calls - calls_before
        payload["metadata"]["generation_cache_hits_last_command"] = store.hits
        save_baseline(directory, payload)
        print(f"{row['id']}: {row['generation_status']}", flush=True)
        if row["generation_status"] == "quota_pending":
            print("Cuota diaria: estado guardado; reanuda con el mismo comando.")
            return 2
    payload["metadata"]["generation_calls_last_command"] = store.calls - calls_before
    payload["metadata"]["generation_cache_hits_last_command"] = store.hits
    save_baseline(directory, payload)
    print(f"Evidencia: {directory}")
    return 1 if any(r["generation_status"] == "api_error" for r in selected) else 0


def register_profile(payload, group, profile):
    profiles = payload["metadata"]["scoring_profiles"]
    if group in profiles and profiles[group] != profile:
        raise ValueError("Cambió el perfil de puntuación; conserva esta evidencia y crea otra corrida")
    profiles[group] = profile


def score_text(payload, selected):
    from rag_eval.text_metrics import score_rouge, text_profile
    register_profile(payload, "text", {**text_profile(), "code_sha256": file_digest(BASE / "text_metrics.py")})
    for row in selected:
        status, reason = metric_eligibility("text", row)
        if reason is None and status != "not_applicable":
            row["metrics"]["text"] = {"status": "ok", "rouge": score_rouge(row["reference"], row["response"])}
        else:
            row["metrics"]["text"] = {"status": status, "reason": reason}


async def score_ragas(directory, payload, selected, args):
    from openai import AsyncOpenAI
    from rag_eval.baseline_report import save_baseline
    from rag_eval.extended_metrics import create_extended_metrics, embedding_profile, local_embeddings, metric_arguments
    from rag_eval.providers import CompletionStore, ENDPOINT, StrictGroqJudge, daily_quota, safe_error

    profile = {"judge_model": payload["metadata"]["judge_model"], "judge_format": "json_schema_strict",
               "reasoning_effort": "low", "max_completion_tokens": 4096, "temperature": 0,
               "prompts": "ragas_original_instructions_without_few_shot_examples",
               "context_precision_variant": "ContextPrecisionWithReference",
               "response_relevancy_class": "AnswerRelevancy", "strictness": 3,
               "response_relevancy_cache": "independent_draw_slots_0_1_2",
               "factual_correctness": {"mode": "f1", "beta": 1.0, "atomicity": "low", "coverage": "low"},
               "versions": versions(("ragas", "openai", "pydantic")),
               "code_sha256": file_digest(BASE / "extended_metrics.py")}
    embeddings = None
    embedding_error = None
    try:
        profile["embeddings"] = embedding_profile(args.embeddings_dir)
        embeddings = local_embeddings(args.embeddings_dir)
    except Exception as error:
        embedding_error = safe_error(error)
        profile["embeddings"] = {"state": "not_ready", **embedding_error}
    # La preparación posterior de embeddings no invalida las otras cuatro métricas.
    saved = payload["metadata"]["scoring_profiles"].get("ragas")
    if saved and saved.get("embeddings", {}).get("state") == "not_ready":
        saved["embeddings"] = profile["embeddings"]
    register_profile(payload, "ragas", profile)
    store = CompletionStore(ROOT / ".local/ragas/cache-v2")
    payload["metadata"].update(judge_calls_last_command=0, judge_cache_hits_last_command=0,
                               judge_cache_misses_last_command=0)
    async def no_network(**kwargs):
        raise CacheMissError("Falta un juicio en caché")
    if args.cache_only:
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=no_network)))
    else:
        from app.settings import load_settings
        settings = load_settings()
        if not settings.groq_api_key:
            raise ValueError("Falta configurar Groq")
        client = AsyncOpenAI(api_key=settings.groq_api_key, base_url=ENDPOINT, timeout=60, max_retries=0)
    judge = StrictGroqJudge(client, profile["judge_model"], store)
    scorers = create_extended_metrics(judge, embeddings)
    stop_for_quota = False
    try:
        # Recuperación primero: se puede puntuar aunque no exista respuesta.
        for name in RAGAS_METRICS:
            for row in selected:
                status, reason = metric_eligibility(name, row)
                if reason is not None or status == "not_applicable":
                    row["metrics"][name] = {"status": status, "reason": reason}
                    continue
                if row["metrics"].get(name, {}).get("status") == "ok":
                    continue
                if name == "response_relevancy" and embeddings is None:
                    row["metrics"][name] = {"status": "dependency_pending", "reason": "embeddings_not_ready", **embedding_error}
                elif stop_for_quota:
                    row["metrics"][name] = {"status": "quota_pending", "reason": "judge_daily_quota"}
                else:
                    try:
                        value = float((await scorers[name].ascore(**metric_arguments(name, row))).value)
                        if not math.isfinite(value) or not 0 <= value <= 1:
                            raise ValueError("Puntuación fuera de rango")
                        row["metrics"][name] = {"status": "ok", "value": value, "provenance": "ragas_saved_inputs"}
                    except Exception as error:
                        stop_for_quota = bool(daily_quota(error))
                        state = "quota_pending" if stop_for_quota else "cache_miss" if isinstance(error, CacheMissError) else "error"
                        row["metrics"][name] = {"status": state, **safe_error(error)}
                payload["metadata"]["judge_calls_last_command"] = 0 if args.cache_only else store.calls
                payload["metadata"]["judge_cache_misses_last_command"] = store.calls if args.cache_only else 0
                payload["metadata"]["judge_cache_hits_last_command"] = store.hits
                save_baseline(directory, payload)
                print(f"{row['id']}: {name}={row['metrics'][name]['status']}", flush=True)
    finally:
        if not args.cache_only:
            await client.close()


def score(args):
    from rag_eval.baseline_report import save_baseline
    directory = local_directory(args.run)
    payload = load_run(directory)
    selected = select_cases(payload["results"], args.only, args.limit)
    payload["metadata"]["last_scoring_selection"] = [row["id"] for row in selected]
    if args.group in {"text", "all"}:
        score_text(payload, selected)
        save_baseline(directory, payload)
    if args.group in {"ragas", "all"}:
        asyncio.run(score_ragas(directory, payload, selected, args))
    summary = save_baseline(directory, payload)
    print(json.dumps(summary["all"], ensure_ascii=True, indent=2))
    print(f"Reporte: {directory / 'report.md'}")
    requested = list(RAGAS_METRICS) if args.group == "ragas" else ["text"] if args.group == "text" else [*RAGAS_METRICS, "text"]
    incomplete = any(r["metrics"][name]["status"] not in {"ok", "not_applicable"} for r in selected for name in requested)
    return 2 if incomplete else 0


def main():
    isolate_process()
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    audit = commands.add_parser("audit", help="Inventario local por ID de las corridas históricas.")
    audit.add_argument("--output", type=Path, default=ROOT / ".local/ragas/baseline-audit")
    embeddings = commands.add_parser("prepare-embeddings", help="Descarga explícita y manifiesto del modelo multilingüe.")
    embeddings.add_argument("--embeddings-dir", type=Path, default=DEFAULT_EMBEDDINGS)
    generation = commands.add_parser("generate", help="Genera o reanuda; conserva respuestas terminadas.")
    generation.add_argument("--reuse-run", type=Path, action="append")
    generation.add_argument("--prepare-only", action="store_true")
    generation.add_argument("--judge-model", default="openai/gpt-oss-120b")
    scoring = commands.add_parser("score", help="Puntúa respuestas guardadas; text funciona sin Groq ni embeddings.")
    scoring.add_argument("--group", choices=("text", "ragas", "all"), default="text")
    scoring.add_argument("--cache-only", action="store_true", help="Prohíbe llamadas al juez; usa solo juicios guardados.")
    scoring.add_argument("--embeddings-dir", type=Path, default=DEFAULT_EMBEDDINGS)
    for command in (generation, scoring):
        command.add_argument("--run", type=Path, required=True)
        command.add_argument("--only", nargs="+")
        command.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()
    if args.command == "audit":
        return audit_history(args.output)
    if args.command == "prepare-embeddings":
        from rag_eval.extended_metrics import prepare_embeddings
        profile = prepare_embeddings(local_directory(args.embeddings_dir))
        print(f"Modelo: {profile['model']}; revisión: {profile['revision']}")
        return 0
    return generate(args) if args.command == "generate" else score(args)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        # No mostrar el texto de excepciones: puede contener entradas o secretos.
        print("Evaluación detenida. Tipo:", type(error).__name__)
        raise SystemExit(1)
