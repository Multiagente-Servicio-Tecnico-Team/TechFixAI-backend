"""Ingesta determinista y versionada del corpus Markdown compartido."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Iterable

from langchain_core.documents import Document
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter

from app.rag.constants import COLLECTION_NAME, CORPUS_VERSION, EMBEDDING_MODEL
from app.rag.sources import KnowledgeSource, knowledge_sources

BASE_DIR = Path(__file__).resolve().parents[2]
KNOWLEDGE_DIR = BASE_DIR / "data" / "knowledge"
CHROMA_DIR = BASE_DIR / "data" / "chroma"


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def cargar_documentos(sources: Iterable[KnowledgeSource] | None = None) -> list[Document]:
    documents: list[Document] = []
    for source in sources if sources is not None else knowledge_sources():
        text = source.path.read_text(encoding="utf-8").strip()
        if not text:
            continue
        documents.append(
            Document(
                page_content=text,
                metadata={
                    "source_id": source.source_id,
                    "source_path": _relative_source_path(source.path),
                    "source": source.path.name,
                    "area": source.area,
                    "trust_level": source.trust_level,
                    "customer_facts_allowed": str(source.customer_facts_allowed).lower(),
                    "audience": source.audience,
                    "language": source.language,
                    "source_version": source.version,
                },
            )
        )
    return documents


def _relative_source_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(BASE_DIR.resolve()).as_posix()
    except ValueError:
        return path.name


def dividir_documentos(documentos: Iterable[Document]) -> list[Document]:
    header_splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=[("#", "title"), ("##", "section"), ("###", "subsection")],
        strip_headers=False,
    )
    size_splitter = RecursiveCharacterTextSplitter(chunk_size=700, chunk_overlap=100)
    chunks: list[Document] = []
    for document in documentos:
        sections = header_splitter.split_text(document.page_content)
        if not sections:
            sections = [Document(page_content=document.page_content)]
        for section in sections:
            merged = {**document.metadata, **section.metadata}
            for part in size_splitter.split_documents([Document(page_content=section.page_content, metadata=merged)]):
                content = part.page_content.strip()
                if not content:
                    continue
                digest = _digest(content)
                part.metadata.update(
                    content_digest=digest,
                    corpus_version=CORPUS_VERSION,
                    embedding_model=EMBEDDING_MODEL,
                    chunk_id=_digest(f"{document.metadata['source_id']}:{part.metadata.get('section', '')}:{digest}")[:32],
                )
                chunks.append(part)
    # Exact content duplicates collapse to one vector while retaining source ids.
    unique: dict[str, Document] = {}
    for chunk in chunks:
        key = chunk.metadata["content_digest"]
        if key not in unique:
            unique[key] = chunk
        else:
            references = set(unique[key].metadata.get("source_refs", "").split(","))
            references.update({unique[key].metadata["source_id"], chunk.metadata["source_id"]})
            unique[key].metadata["source_refs"] = ",".join(sorted(filter(None, references)))
    return list(unique.values())


def crear_embeddings():
    # La dependencia de FastEmbed se carga solo cuando se construye el índice
    # vectorial explícitamente; la API léxica no necesita importar el modelo.
    from app.rag.embeddings import create_embeddings

    return create_embeddings()


def _load_vectorstore_class():
    """Importa Chroma solo cuando se solicita construir el índice híbrido."""
    from langchain_chroma import Chroma

    return Chroma


def crear_base_vectorial():
    # La ruta de ingesta vectorial se conserva para habilitar el modo híbrido
    # en el futuro. No se ejecuta al iniciar ni al consultar el RAG léxico.
    documents = cargar_documentos()
    if not documents:
        raise RuntimeError("No se encontraron documentos Markdown en las fuentes registradas.")
    chunks = dividir_documentos(documents)
    ids = [chunk.metadata["chunk_id"] for chunk in chunks]
    vectorstore = _load_vectorstore_class()(
        collection_name=COLLECTION_NAME,
        embedding_function=crear_embeddings(),
        persist_directory=str(CHROMA_DIR),
        collection_metadata={"corpus_version": CORPUS_VERSION, "embedding_model": EMBEDDING_MODEL},
    )
    # Reconcile only the new versioned collection. Older collections remain intact
    # for rollback until an explicit cleanup is approved.
    existing = vectorstore.get(include=[]).get("ids", [])
    stale = sorted(set(existing) - set(ids))
    if stale:
        vectorstore.delete(ids=stale)
    vectorstore.add_documents(chunks, ids=ids)
    return vectorstore, documents, chunks


if __name__ == "__main__":
    _, documents, chunks = crear_base_vectorial()
    print(f"Índice {COLLECTION_NAME} actualizado: {len(documents)} fuentes, {len(chunks)} fragmentos.")
