from langchain_core.documents import Document

from app.rag.retriever import retrieve_documents


def _corpus():
    return [
        Document(
            page_content="Si el equipo no enciende, verifica primero la alimentacion externa.",
            metadata={
                "source_id": "technical:power",
                "source_path": "manuales/energia.md",
                "title": "Equipo sin encender",
                "section": "Comprobaciones externas",
                "content_digest": "power-digest",
                "area": "technical",
                "trust_level": "verified_guide",
                "audience": "customer",
                "language": "es",
                "corpus_version": "test-v1",
            },
        ),
        Document(
            page_content="Horario de atención: la tienda de ejemplo atiende de 9 a 5.",
            metadata={
                "source_id": "business:faq",
                "source_path": "data/knowledge/faq.md",
                "title": "Horario de atencion",
                "section": "Horario",
                "content_digest": "demo-digest",
                "area": "faq",
                "trust_level": "demo_only",
                "audience": "customer",
                "language": "es",
                "corpus_version": "test-v1",
            },
        ),
    ]


def test_shared_rag_returns_same_provenance_and_abstains_without_evidence():
    corpus = _corpus()
    first = retrieve_documents("computadora no enciende", documents=corpus)
    second = retrieve_documents("computadora no enciende", documents=corpus)

    assert first == second
    assert [item.source_id for item in first] == ["technical:power"]
    assert first[0].source_path == "manuales/energia.md"
    assert first[0].trust_level == "verified_guide"
    assert retrieve_documents("como reparar un satelite", documents=corpus) == []


def test_demo_faq_passages_are_labeled_and_excluded_from_verified_answers(monkeypatch):
    corpus = _corpus()
    verified = retrieve_documents(
        "horario de atencion",
        documents=corpus,
        allowed_trust_levels={"verified_guide", "technical_reference"},
    )
    demo = retrieve_documents(
        "horario de atencion",
        documents=corpus,
        allowed_areas={"faq"},
    )

    assert verified == []
    assert demo and demo[0].trust_level == "demo_only"
    assert demo[0].source_path == "data/knowledge/faq.md"
    assert "Horario" in demo[0].section

    import app.rag.tools as rag_tools

    monkeypatch.setattr(rag_tools, "retrieve_documents", lambda *args, **kwargs: demo)
    answer_context = rag_tools.consultar_base_conocimiento.invoke(
        {"consulta": "horario de atención"}
    )
    assert "confianza: demo_only" in answer_context
    assert "data/knowledge/faq.md" in answer_context
