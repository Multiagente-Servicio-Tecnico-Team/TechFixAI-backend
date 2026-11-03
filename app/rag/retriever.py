"""Retrieval compartido con abstención y metadatos de procedencia."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from typing import Iterable

from langchain_chroma import Chroma
from langchain_core.documents import Document

from app.rag.embeddings import COLLECTION_NAME, EMBEDDING_MODEL, create_embeddings

BASE_DIR = __import__("pathlib").Path(__file__).resolve().parents[2]
CHROMA_DIR = BASE_DIR / "data" / "chroma"
_QUERY_STOP_WORDS = {
    "ademas", "algo", "alguna", "algunas", "algunos", "como", "con", "cuando",
    "de", "del", "desde", "donde", "el", "ella", "ellos", "en", "es", "esta",
    "este", "estoy", "funciona", "hay", "la", "las", "lo", "los", "mi", "mis",
    "mucho", "muy", "no", "para", "pero", "por", "problema", "que", "se", "sin",
    "su", "tengo", "un", "una", "unas", "unos", "y", "atencion",
    "consulta", "sobre", "equipo", "laptop", "laptops",
}


@dataclass(frozen=True)
class RetrievedPassage:
    content: str
    source_id: str
    source_path: str
    title: str
    section: str
    content_digest: str
    area: str
    trust_level: str
    audience: str
    language: str
    corpus_version: str
    embedding_model: str
    score: float
    match_type: str


def _normalize(text: str) -> str:
    value = unicodedata.normalize("NFKD", text.casefold())
    value = "".join(char for char in value if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", value).strip()


def _metadata(document: Document) -> dict[str, str]:
    return {str(key): str(value) for key, value in document.metadata.items()}


def _passage(document: Document, score: float, match_type: str) -> RetrievedPassage:
    metadata = _metadata(document)
    return RetrievedPassage(
        content=document.page_content[:4000],
        source_id=metadata.get("source_id", metadata.get("source", "unknown")),
        source_path=metadata.get("source_path", ""),
        title=metadata.get("title", ""),
        section=metadata.get("section", ""),
        content_digest=metadata.get("content_digest", ""),
        area=metadata.get("area", "general"),
        trust_level=metadata.get("trust_level", "unverified"),
        audience=metadata.get("audience", "internal"),
        language=metadata.get("language", "es"),
        corpus_version=metadata.get("corpus_version", "1"),
        embedding_model=metadata.get("embedding_model", EMBEDDING_MODEL),
        score=score,
        match_type=match_type,
    )


def retrieve_documents(
    query: str,
    *,
    documents: Iterable[Document] | None = None,
    allowed_trust_levels: set[str] | None = None,
    allowed_areas: set[str] | None = None,
    allowed_sources: set[str] | None = None,
    limit: int = 3,
) -> list[RetrievedPassage]:
    if limit < 1:
        raise ValueError("El límite de recuperación debe ser mayor que cero.")
    query_norm = _normalize(query)
    if not query_norm:
        return []
    semantic_corpus = [] if documents is not None else _search_index(query, limit)
    if documents is None:
        from app.rag.ingest import cargar_documentos, dividir_documentos

        lexical_corpus = dividir_documentos(cargar_documentos())
        corpus = semantic_corpus + lexical_corpus
    else:
        corpus = list(documents)
    allowed = allowed_trust_levels
    scored: list[tuple[float, Document, str]] = []
    code_query = bool(re.search(r"[A-Z]{2,}[\w-]*\d[\w-]*|\b\d{3,}\b", query, re.I))
    for document in corpus:
        metadata = _metadata(document)
        trust = metadata.get("trust_level", "unverified")
        if allowed is not None and trust not in allowed:
            continue
        if allowed_areas is not None and metadata.get("area") not in allowed_areas:
            continue
        if allowed_sources is not None:
            source_refs = set(metadata.get("source_refs", "").split(","))
            source_refs.add(metadata.get("source_id", ""))
            if not source_refs.intersection(allowed_sources):
                continue
        content_norm = _normalize(" ".join((
            document.page_content,
            metadata.get("title", ""),
            metadata.get("section", ""),
        )))
        semantic_score = float(metadata.get("_semantic_score", "0"))
        if semantic_score >= 0.35:
            scored.append((semantic_score, document, "semantic"))
        if code_query and query_norm in content_norm:
            scored.append((1.0, document, "lexical_code"))
            continue
        query_tokens = {
            token
            for token in re.findall(r"[a-z0-9]{3,}", query_norm)
            if token not in _QUERY_STOP_WORDS
        }
        content_tokens = set(re.findall(r"[a-z0-9]{3,}", content_norm))
        overlap = len(query_tokens & content_tokens)
        coverage = overlap / max(len(query_tokens), 1)
        # Lexical-only matches need stronger query coverage to avoid turning a
        # single generic word (for example "atención") into an answer.
        if coverage >= 0.34:
            match_type = "hybrid" if semantic_score >= 0.35 else "lexical"
            scored.append((max(coverage, semantic_score), document, match_type))
    scored.sort(key=lambda item: (-item[0], _metadata(item[1]).get("source_id", "")))
    deduplicated: list[tuple[float, Document, str]] = []
    seen_content: set[str] = set()
    for item in scored:
        digest = _metadata(item[1]).get("content_digest") or item[1].page_content
        if digest in seen_content:
            continue
        seen_content.add(digest)
        deduplicated.append(item)
    scored = deduplicated
    if not scored:
        return []
    top = scored[0][0]
    # Require at least a meaningful term overlap; exact codes are handled above.
    if scored[0][2] != "lexical_code" and top < 0.25:
        return []
    return [_passage(doc, score, kind) for score, doc, kind in scored[:limit]]


def _search_index(query: str, limit: int) -> list[Document]:
    try:
        vectorstore = obtener_vectorstore()
        matches = vectorstore.similarity_search_with_relevance_scores(query, k=max(limit * 3, 6))
    except Exception:
        # The local lexical corpus remains useful while the versioned vector index
        # is not built or the optional embedding model is unavailable.
        matches = []
    results = []
    for doc, score in matches:
        if score < 0.25:
            continue
        doc.metadata["_semantic_score"] = float(score)
        results.append(doc)
    return results


@lru_cache(maxsize=1)
def obtener_vectorstore() -> Chroma:
    return Chroma(
        collection_name=COLLECTION_NAME,
        embedding_function=create_embeddings(),
        persist_directory=str(CHROMA_DIR),
    )
