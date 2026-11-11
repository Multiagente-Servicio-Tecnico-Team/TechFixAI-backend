"""Adaptador de compatibilidad sobre el RAG común."""
from app.rag.retriever import retrieve_documents


def retrieve_technical_knowledge(query: str, limit: int = 3) -> list[str]:
    passages = retrieve_documents(
        query,
        allowed_trust_levels={"verified_guide", "technical_reference"},
        allowed_areas={"technical"},
        limit=limit,
    )
    return [
        f"Fuente: {passage.source_path or passage.source_id} "
        f"(sección: {passage.section or passage.title or 'sin título'}; "
        f"confianza: {passage.trust_level}; score: {passage.score:.2f})\n"
        f"{passage.content}"
        for passage in passages
    ]
