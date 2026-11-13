"""Estado y procedencia para separar generación, reanudación y puntuación."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import subprocess

from rag_eval.evaluate_project import BASE, ROOT, load_dataset, source_manifest

RAGAS_METRICS = ("context_precision", "context_recall", "faithfulness", "response_relevancy", "factual_correctness")
GENERATION_PACKAGES = ("langchain-groq", "groq", "langchain-core", "pydantic")


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def file_digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def versions(names):
    return {name: importlib.metadata.version(name) for name in names}


def select_cases(rows, identifiers=None, limit=0):
    if limit < 0:
        raise ValueError("El límite no puede ser negativo")
    if identifiers and set(identifiers) - {row["id"] for row in rows}:
        raise ValueError("Hay IDs desconocidos")
    selected = [row for row in rows if not identifiers or row["id"] in identifiers]
    return selected[:limit] if limit else selected


def local_directory(path):
    path = Path(path).resolve()
    if not path.is_relative_to((ROOT / ".local/ragas").resolve()):
        raise ValueError("La evidencia debe estar dentro de .local/ragas")
    return path


def generation_config(settings):
    from rag_eval.native_provider import native_profile
    dataset, samples, dataset_hash = load_dataset(BASE / "dataset_project.json")
    return {
        "schema_version": 1, "scope": dataset["scope"], "dataset_sha256": dataset_hash,
        "dataset_version": dataset["schema_version"], "source_sha256": source_manifest(),
        "model": settings.groq_model, "generator_transport": "backend",
        "native_model_profile": native_profile(settings), "retrieval_mode": settings.rag_retrieval_mode,
        "retrieval_limit": 3, "versions": versions(GENERATION_PACKAGES),
        "runner_sha256": {name: file_digest(BASE / name) for name in ("baseline.py", "baseline_state.py")},
        "reference_review": dataset["reference_review"], "faq_notice": dataset["faq_notice"],
        "case_ids": [sample["id"] for sample in samples],
    }


def new_case(sample, prepared):
    contexts = prepared["contexts"]
    if "\n\n".join(contexts) != prepared["context"]:
        raise ValueError("Los fragmentos no reconstruyen el contexto del componente")
    return {**sample, "category": sample["route"] if sample["answerable"] else "out_of_corpus",
            "retrieved_contexts": contexts, "context_sent_to_generator": None,
            "prepared_context": prepared["context"], "context_order": list(range(1, len(contexts) + 1)),
            "source_ids": prepared["source_ids"], "retrieval_status": "context" if contexts else "no_context",
            "generation_status": "pending", "response": None, "diagnosis": None, "errors": [],
            "generator_invoked": False, "generation_evidence": None, "abstention": None,
            "metrics": {}, "created_at_utc": now()}


def new_run(config, rows, judge_model):
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    branch = subprocess.run(["git", "branch", "--show-current"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    return {"metadata": {"format": "techfix_rag_baseline_v1", "generation_config": config,
                         "generation_fingerprint": digest(config), "git_commit": commit, "branch": branch,
                         "judge_model": judge_model, "created_at_utc": now(), "historical_imports": [],
                         "environment": {"python": platform.python_version(), "platform": platform.platform(),
                                         "packages": {d.metadata["Name"]: d.version for d in importlib.metadata.distributions() if d.metadata.get("Name")}},
                         "dependency_lock_sha256": file_digest(BASE / "requirements-lock.txt"),
                         "scoring_profiles": {}, "scope_note": "Componentes técnicos jerárquicos y FAQ; no HTTP ni grafos completos."},
            "results": rows}


def validate_run(payload, config=None):
    if payload["metadata"].get("format") != "techfix_rag_baseline_v1":
        raise ValueError("Formato no admitido; importa la corrida histórica con --reuse-run")
    saved = payload["metadata"]["generation_config"]
    if payload["metadata"]["generation_fingerprint"] != digest(saved):
        raise ValueError("Configuración alterada")
    if config is not None and digest(config) != digest(saved):
        raise ValueError("Cambió la configuración de generación; crea una corrida nueva")
    dataset, samples, dataset_hash = load_dataset(BASE / "dataset_project.json")
    if dataset_hash != saved["dataset_sha256"]:
        raise ValueError("El dataset cambió")
    expected = {sample["id"]: sample for sample in samples}
    if len({r["id"] for r in payload["results"]}) != len(payload["results"]):
        raise ValueError("IDs duplicados en la evidencia")
    for row in payload["results"]:
        sample = expected.get(row["id"])
        if sample is None or any(row.get(k) != v for k, v in sample.items()):
            raise ValueError("Un caso no coincide con el dataset congelado")
        contexts = row["retrieved_contexts"]
        if "\n\n".join(contexts) != row["prepared_context"]:
            raise ValueError("Orden o contenido de contexto alterado")
        if row["generator_invoked"] and row["context_sent_to_generator"] != row["prepared_context"]:
            raise ValueError("No coincide el contexto entregado al generador")
        if row["context_order"] != list(range(1, len(contexts) + 1)):
            raise ValueError("Orden de fragmentos inválido")
    return payload


def load_run(directory, config=None):
    directory = local_directory(directory)
    return validate_run(json.loads((directory / "results.json").read_text(encoding="utf-8")), config)


def merge_historical(payload, evidence, path):
    """Importa respuestas nativas compatibles; nunca mezcla generadores 20B/120B."""
    meta = evidence["metadata"]
    config = payload["metadata"]["generation_config"]
    required = ("dataset_sha256", "source_sha256", "model", "generator_transport", "native_model_profile", "retrieval_mode", "retrieval_limit")
    if any(meta.get(name) != config[name] for name in required):
        raise ValueError("La corrida histórica difiere en modelo, dataset, corpus o configuración")
    if any(meta.get("versions", {}).get(n) != config["versions"][n] for n in ("pydantic",)):
        raise ValueError("Las dependencias de generación difieren")
    rows = {row["id"]: row for row in payload["results"]}
    imported = []
    for old in evidence["results"]:
        if old["id"] not in rows:
            continue
        row = rows[old["id"]]
        fields = ("user_input", "reference", "route", "answerable", "retrieved_contexts")
        if any(old.get(name) != row.get(name) for name in fields):
            raise ValueError("Los datos o los contextos históricos no coinciden")
        if old.get("response") and not row.get("response"):
            if old.get("context_sent_to_generator") != row["prepared_context"]:
                raise ValueError("La evidencia histórica no identifica el contexto real")
            row.update(response=old["response"], diagnosis=old.get("diagnosis"), generation_status="ok",
                       generator_invoked=bool(row["retrieved_contexts"]),
                       context_sent_to_generator=row["prepared_context"] if row["retrieved_contexts"] else None,
                       generation_evidence={"run": str(path), "sha256": digest(old), "git_commit": meta["git_commit"]})
            imported.append(row["id"])
            if meta.get("judge_model") == payload["metadata"]["judge_model"] and meta.get("metric_prompt_profile") == "ragas_original_instructions_without_few_shot_examples" and meta.get("versions", {}).get("ragas") == importlib.metadata.version("ragas"):
                for name in ("context_precision", "context_recall", "faithfulness"):
                    if old.get(name) is not None:
                        row["metrics"][name] = {"status": "ok", "value": old[name], "provenance": "verified_historical_run", "run": str(path)}
        elif old.get("status") == "quota_exhausted" and not row.get("response"):
            row["generation_status"] = "quota_pending"
    payload["metadata"]["historical_imports"].append({"run": str(path), "evidence_sha256": digest(evidence), "imported_ids": imported})
    return imported


def metric_eligibility(name, row):
    response = isinstance(row.get("response"), str) and bool(row["response"].strip())
    reference = row["answerable"] and bool(row.get("reference", "").strip())
    contexts = bool(row["retrieved_contexts"])
    if name in {"context_precision", "context_recall"}:
        return ("pending", None) if reference and contexts else ("not_applicable", "no_reference" if not reference else "no_context")
    if name == "faithfulness" and not contexts:
        return "not_applicable", "no_context"
    if name in {"factual_correctness", "text"} and not reference:
        return "not_applicable", "no_reference"
    if not response:
        if row.get("generation_status") in {"no_context", "not_applicable"}:
            return "not_applicable", "component_produced_no_response"
        return "pending", "no_response"
    return "pending", None
