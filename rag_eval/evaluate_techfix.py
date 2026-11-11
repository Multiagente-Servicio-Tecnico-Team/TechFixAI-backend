"""Evaluación del recuperador compartido con un prompt de prueba, fuera del chat."""
import argparse
import asyncio
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
from statistics import mean

from openai import AsyncOpenAI
from ragas.llms import llm_factory
from ragas.metrics.collections import ContextPrecision, ContextRecall, Faithfulness

from app.rag.retriever import retrieve_documents
from app.settings import load_settings

BASE = Path(__file__).resolve().parent
ROOT = BASE.parent
METRICS = ("faithfulness", "context_precision", "context_recall")


def save_results(output, rows, metadata):
    summary = {}
    for name in METRICS:
        values = [row[name] for row in rows if isinstance(row.get(name), (int, float))]
        summary[name] = {"mean": mean(values) if values else None, "evaluated": len(values)}
    payload = {"metadata": metadata, "completed_cases": len(rows), "summary": summary, "results": rows}
    (output / "results.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    fields = ["id", "status", "context_count", *METRICS, "failed_metrics"]
    with (output / "results.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Solo recuperación local; no llama a Groq.")
    parser.add_argument("--limit", type=int, default=0, help="0 ejecuta todo el dataset.")
    args = parser.parse_args()
    if args.limit < 0:
        parser.error("--limit debe ser mayor o igual a cero")
    raw = (BASE / "dataset_techfix.json").read_bytes()
    samples = json.loads(raw)
    if args.limit:
        samples = samples[:args.limit]
    settings = load_settings()
    prepared = []
    for sample in samples:
        passages = retrieve_documents(sample["user_input"], allowed_areas={"technical"}, allowed_trust_levels={"verified_guide"}, limit=3)
        prepared.append((sample, passages))
        print(f"{sample['id']}: {len(passages)} fragmentos", flush=True)
    if args.dry_run:
        print("Verificación local terminada. No se llamó a Groq.")
        return
    if not settings.groq_api_key or not settings.groq_model:
        raise ValueError("Falta la configuración de Groq")
    output = ROOT / ".local" / "ragas" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output.mkdir(parents=True, exist_ok=False)
    metadata = {
        "scope": "shared_retriever_with_test_prompt_not_chat",
        "model": settings.groq_model,
        "judge_model": settings.groq_model,
        "same_model_for_generation_and_judging": True,
        "retrieval_mode": settings.rag_retrieval_mode,
        "retrieval_limit": 3,
        "dataset_sha256": hashlib.sha256(raw).hexdigest(),
        "planned_cases": len(samples),
        "missing_scores": "null, excluidos de los promedios; revisar estados y denominadores",
    }
    rows = []
    async with AsyncOpenAI(api_key=settings.groq_api_key, base_url="https://api.groq.com/openai/v1", max_retries=1, timeout=90) as client:
        judge = llm_factory(settings.groq_model, provider="openai", client=client, temperature=0, max_tokens=8192)
        scorers = {"faithfulness": Faithfulness(llm=judge), "context_precision": ContextPrecision(llm=judge), "context_recall": ContextRecall(llm=judge)}
        for sample, passages in prepared:
            contexts = [part.content for part in passages]
            row = {**sample, "context_count": len(contexts), "retrieved_contexts": contexts, "sources": [part.source_id for part in passages], "response": None, "status": "pending", "failed_metrics": [], **dict.fromkeys(METRICS)}
            if not contexts:
                row["status"] = "no_context" if sample["answerable"] else "expected_abstention"
            else:
                try:
                    completion = await client.chat.completions.create(
                        model=settings.groq_model, temperature=0,
                        messages=[{"role": "system", "content": "Eres un asistente de soporte técnico. Responde en español usando únicamente el contexto. Distingue causas posibles de diagnósticos confirmados. Si falta información, indícalo.\n\nContexto:\n" + "\n\n".join(contexts)}, {"role": "user", "content": sample["user_input"]}],
                    )
                    row["response"] = completion.choices[0].message.content or ""
                    if not row["response"].strip():
                        raise ValueError("Respuesta vacía")
                    row["status"] = "unexpected_context" if not sample["answerable"] else "ok"
                except Exception as error:
                    row.update(status="generation_error", error_type=type(error).__name__, http_status=getattr(error, "status_code", None))
                if row["response"] and sample["answerable"]:
                    for name, scorer in scorers.items():
                        print(f"{sample['id']}: evaluando {name}", flush=True)
                        try:
                            arguments = {"user_input": sample["user_input"], "retrieved_contexts": contexts}
                            arguments.update({"response": row["response"]} if name == "faithfulness" else {"reference": sample["reference"]})
                            score = float((await scorer.ascore(**arguments)).value)
                            if not math.isfinite(score):
                                raise ValueError("Puntuación no finita")
                            row[name] = score
                        except Exception as error:
                            row["failed_metrics"].append({"metric": name, "error_type": type(error).__name__, "http_status": getattr(error, "status_code", None)})
                    if row["failed_metrics"]:
                        row["status"] = "metric_error"
            rows.append(row)
            save_results(output, rows, metadata)
            print(f"{sample['id']}: {row['status']} | " + " | ".join(f"{name}={row[name]}" for name in METRICS), flush=True)
    print(f"Resultados guardados en: {output}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as error:
        print(f"Evaluación detenida. Tipo: {type(error).__name__}; HTTP: {getattr(error, 'status_code', None)}")
        raise SystemExit(1)