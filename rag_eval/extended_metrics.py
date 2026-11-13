"""Métricas compatibles con Ragas 0.4.3 y embeddings multilingües locales."""
from __future__ import annotations

import asyncio
import hashlib
import importlib.metadata
import json
from pathlib import Path

MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
MODEL_REPO = "qdrant/paraphrase-multilingual-MiniLM-L12-v2-onnx-Q"
REQUIRED_FILES = ("model_optimized.onnx", "tokenizer.json", "tokenizer_config.json", "config.json", "special_tokens_map.json")


def digest_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def prepare_embeddings(directory):
    """Solo descarga pesos públicos; nunca envía preguntas ni respuestas."""
    from huggingface_hub import HfApi, hf_hub_download
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    revision = HfApi(token=False).model_info(MODEL_REPO).sha
    for name in REQUIRED_FILES:
        hf_hub_download(MODEL_REPO, name, revision=revision, local_dir=directory, token=False)
    profile = {"model": MODEL, "repository": MODEL_REPO, "revision": revision,
               "files_sha256": {name: digest_file(directory / name) for name in REQUIRED_FILES},
               "provider": "fastembed_onnx_cpu_local", "prefix": None,
               "versions": {n: importlib.metadata.version(n) for n in ("fastembed", "onnxruntime", "tokenizers")}}
    (directory / "embedding_manifest.json").write_text(json.dumps(profile, indent=2), encoding="utf-8")
    return profile


def embedding_profile(directory):
    directory = Path(directory)
    profile = json.loads((directory / "embedding_manifest.json").read_text(encoding="utf-8"))
    if profile["model"] != MODEL or profile["repository"] != MODEL_REPO:
        raise ValueError("Modelo de embeddings inesperado")
    if set(profile["files_sha256"]) != set(REQUIRED_FILES):
        raise ValueError("Manifiesto de embeddings incompleto")
    for name, digest in profile["files_sha256"].items():
        if digest_file(directory / name) != digest:
            raise ValueError("Cambió un archivo del modelo de embeddings")
    if profile["versions"] != {n: importlib.metadata.version(n) for n in profile["versions"]}:
        raise ValueError("Cambió el runtime de embeddings")
    return profile


def local_embeddings(directory):
    """La puntuación exige pesos ya preparados; no descarga nada implícitamente."""
    from fastembed import TextEmbedding
    from ragas.embeddings.base import BaseRagasEmbedding
    embedding_profile(directory)

    class LocalMultilingualEmbeddings(BaseRagasEmbedding):
        def __init__(self):
            super().__init__()
            self.encoder = TextEmbedding(MODEL, specific_model_path=str(Path(directory).resolve()),
                                         local_files_only=True, threads=2, providers=["CPUExecutionProvider"])

        def embed_text(self, text, **kwargs):
            return next(self.encoder.embed([text])).tolist()

        async def aembed_text(self, text, **kwargs):
            return await asyncio.to_thread(self.embed_text, text)

    return LocalMultilingualEmbeddings()


def create_extended_metrics(judge, embeddings=None):
    from ragas.metrics.collections import AnswerRelevancy, FactualCorrectness
    from rag_eval.metrics import create_metrics
    scorers = create_metrics(judge)
    factual = FactualCorrectness(llm=judge, mode="f1", beta=1.0, atomicity="low", coverage="low")
    factual.prompt.examples = []
    factual.nli_prompt.examples = []
    scorers["factual_correctness"] = factual
    if embeddings is not None:
        from ragas.llms.base import InstructorBaseRagasLLM
        from rag_eval.providers import StrictGroqJudge

        class DrawStore:
            def __init__(self, store, draw):
                self.store, self.draw = store, draw

            @property
            def calls(self):
                return self.store.calls

            @calls.setter
            def calls(self, value):
                self.store.calls = value

            def read(self, payload):
                return self.store.read({"relevance_draw": self.draw, "request": payload})

            def write(self, payload, content):
                self.store.write({"relevance_draw": self.draw, "request": payload}, content)

        class DrawJudge(InstructorBaseRagasLLM):
            def generate(self, prompt, response_model):
                raise RuntimeError("Usa la API asíncrona")

            async def agenerate(self, prompt, response_model):
                draw = self.draw
                self.draw += 1
                scoped = StrictGroqJudge(judge.client, judge.model, DrawStore(judge.store, draw))
                return await scoped.agenerate(prompt, response_model)

        class IndependentlyCachedRelevancy(AnswerRelevancy):
            async def ascore(self, user_input, response):
                self.llm.draw = 0
                return await super().ascore(user_input=user_input, response=response)

        # Tres inferencias con entradas iguales necesitan tres entradas de caché;
        # no alterar la fórmula ni añadir instrucciones al prompt del juez.
        relevancy = IndependentlyCachedRelevancy(llm=DrawJudge(), embeddings=embeddings, strictness=3)
        relevancy.prompt.examples = []
        scorers["response_relevancy"] = relevancy
    return scorers


def metric_arguments(name, row):
    if name in {"context_precision", "context_recall"}:
        return {"user_input": row["user_input"], "reference": row["reference"], "retrieved_contexts": row["retrieved_contexts"]}
    if name == "faithfulness":
        return {"user_input": row["user_input"], "response": row["response"], "retrieved_contexts": row["retrieved_contexts"]}
    if name == "response_relevancy":
        return {"user_input": row["user_input"], "response": row["response"]}
    return {"reference": row["reference"], "response": row["response"]}
