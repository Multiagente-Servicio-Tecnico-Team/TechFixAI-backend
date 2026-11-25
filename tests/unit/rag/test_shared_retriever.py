from pathlib import Path

from langchain_core.documents import Document

from app.rag.retriever import RetrievedPassage, retrieve_documents


def test_retrieval_returns_source_provenance_and_filters_demo_content():
    documents = [
        Document(
            page_content="El diagnóstico inicial requiere revisar la ventilación.",
            metadata={
                "source_id": "manual.hardware",
                "source_path": "manual.md",
                "title": "Ventilación",
                "section": "Revisión inicial",
                "content_digest": "abc123",
                "area": "technical",
                "trust_level": "verified_guide",
                "audience": "customer",
                "language": "es",
                "corpus_version": "v1",
                "embedding_model": "test-model",
            },
        ),
        Document(
            page_content="Dirección de demostración: Calle Falsa 123.",
            metadata={"trust_level": "demo_only", "source_id": "faq.demo"},
        ),
    ]

    results = retrieve_documents(
        "ventilación diagnóstico inicial",
        documents=documents,
        allowed_trust_levels={"verified_guide"},
    )

    assert len(results) == 1
    assert isinstance(results[0], RetrievedPassage)
    assert results[0].source_id == "manual.hardware"
    assert "Calle Falsa" not in results[0].content


def test_lexical_codes_match_exactly_and_irrelevant_queries_abstain():
    documents = [
        Document(
            page_content="SSD NVMe 1TB código `SSD-1TB-X`.",
            metadata={"source_id": "catalog.guide", "trust_level": "verified_guide"},
        ),
    ]

    exact = retrieve_documents("SSD-1TB-X", documents=documents)
    unrelated = retrieve_documents("impresora no escanea", documents=documents)

    assert exact and exact[0].match_type == "lexical_code"
    assert unrelated == []


def test_markdown_sources_come_from_the_single_reviewed_corpus():
    # Spec 011: los tres patrones comparten un solo corpus revisado (base jerárquica) con el mismo nivel de confianza.
    from app.rag.sources import knowledge_sources

    sources = knowledge_sources()
    assert sources
    assert {source.source_id.split(":", 1)[0] for source in sources} == {"hierarchical"}
    assert {source.trust_level for source in sources} == {"verified_guide"}
    faq = next(source for source in sources if source.path.name == "faq_servicio.md")
    assert faq.area == "faq"


def test_vector_relevance_is_preserved_and_low_relevance_abstains(monkeypatch):
    import app.rag.retriever as retrieval

    monkeypatch.setenv("RAG_RETRIEVAL_MODE", "hybrid")

    source = Document(
        page_content="El equipo presenta sobrecalentamiento del procesador.",
        metadata={"source_id": "test:semantic", "trust_level": "verified_guide"},
    )

    class FakeStore:
        def __init__(self, score):
            self.score = score

        def similarity_search_with_relevance_scores(self, query, k):
            return [(source, self.score)]

    monkeypatch.setattr(retrieval, "obtener_vectorstore", lambda: FakeStore(0.82))
    semantic = retrieval.retrieve_documents(
        "fallo térmico en CPU", allowed_sources={"test:semantic"}
    )
    assert semantic[0].match_type == "semantic"
    assert semantic[0].score == 0.82

    monkeypatch.setattr(retrieval, "obtener_vectorstore", lambda: FakeStore(0.1))
    assert retrieval.retrieve_documents(
        "impresora no escanea", allowed_sources={"test:semantic"}
    ) == []
