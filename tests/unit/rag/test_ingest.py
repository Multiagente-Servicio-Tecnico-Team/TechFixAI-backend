from langchain_core.documents import Document

from app.rag.ingest import dividir_documentos


def test_markdown_ingestion_has_source_metadata_and_stable_chunk_ids():
    document = Document(
        page_content="# Manual\n\n## Bateria\n\nRevisar el cargador antes del diagnostico.",
        metadata={"source_id": "test:guide", "source_path": "guide.md", "trust_level": "verified_guide"},
    )

    first = dividir_documentos([document])
    second = dividir_documentos([document])

    assert first[0].metadata["source_id"] == "test:guide"
    assert first[0].metadata["section"] == "Bateria"
    assert first[0].metadata["chunk_id"] == second[0].metadata["chunk_id"]
    assert first[0].metadata["content_digest"] == second[0].metadata["content_digest"]


def test_exact_duplicate_content_is_deduplicated_and_keeps_both_sources():
    documents = [
        Document(page_content="## Shared\n\nIdentical approved guidance.", metadata={"source_id": source})
        for source in ("left", "right")
    ]

    chunks = dividir_documentos(documents)

    assert len(chunks) == 1
    assert set(chunks[0].metadata["source_refs"].split(",")) == {"left", "right"}


def test_reingestion_removes_stale_ids_without_touching_old_collection(monkeypatch):
    import app.rag.ingest as ingest

    current = Document(page_content="Current chunk", metadata={"chunk_id": "current"})

    class FakeVectorStore:
        deleted = []
        added = []

        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def get(self, include):
            return {"ids": ["stale", "current"]}

        def delete(self, ids):
            self.deleted.extend(ids)

        def add_documents(self, documents, ids):
            self.added.extend(ids)

    monkeypatch.setattr(ingest, "cargar_documentos", lambda: [Document(page_content="source")])
    monkeypatch.setattr(ingest, "dividir_documentos", lambda _: [current])
    monkeypatch.setattr(ingest, "Chroma", FakeVectorStore)

    store, _, _ = ingest.crear_base_vectorial()

    assert store.deleted == ["stale"]
    assert store.added == ["current"]
    assert store.kwargs["collection_name"] == ingest.COLLECTION_NAME
