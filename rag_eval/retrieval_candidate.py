"""Propuesta aislada: prepara consultas sin modificar los módulos de app/."""
from __future__ import annotations

import re

# Vocabulario de formulación, no síntomas ni restricciones del equipo.
_QUESTION_FILLERS = {
    "cual", "cuales", "puede", "pueden", "puedes", "podria", "podrian",
    "debe", "deben", "deberia", "deberian", "necesita", "necesito",
    "causa", "causas", "posible", "posibles", "revision", "revisar",
    "tecnico", "tecnica", "tecnicos", "tecnicas", "corresponde",
    "corresponden", "manual", "indica", "indican", "muestra", "presenta",
    "pasando", "ocurre", "problemas", "dime", "ayudarme",
    "computadora", "computadoras", "ordenador", "ordenadores", "notebook",
}
_HEX_CODE = re.compile(r"(?<![\w-])0x[0-9a-f]{4,}(?![\w-])", re.IGNORECASE)
_CONTEXT_CUES = {
    "ayuda", "hacer", "tienda", "local", "atencion", "medio", "medios",
    "forma", "formas", "compra", "comprar", "armado", "gamer", "crear",
    "obtener", "aceptar", "cuanto", "diagnostico", "mano", "obra", "funciona",
}


def prepare_query(question):
    from app.rag.retriever import _normalize
    normalized = _normalize(question)
    codes = list(dict.fromkeys(_HEX_CODE.findall(normalized)))
    if codes:
        return " ".join(codes)
    words = re.findall(r"\w+(?:[-_]\w+)*", normalized)
    return " ".join(word for word in words if word not in _QUESTION_FILLERS)


def retrieve_candidate_faq(question, *, limit=3):
    from app.rag.faq import FAQ_PATH, _FAQ_TOPICS
    from app.rag.retriever import _normalize, load_lexical_corpus, retrieve_documents
    if limit < 1:
        raise ValueError("El límite debe ser positivo")
    normalized = _normalize(question)
    words = re.findall(r"[a-z0-9]{3,}", normalized)
    terms = set(words)
    matches = {name: terms & aliases for name, (aliases, _) in _FAQ_TOPICS.items() if terms & aliases}
    explicit = {name: cues - _CONTEXT_CUES for name, cues in matches.items() if cues - _CONTEXT_CUES}
    chosen = explicit or matches
    # Una petición de ayuda ajena al corpus no implica preguntar por servicios.
    if chosen and set(chosen) == {"servicios"} and not explicit:
        capability = re.search(r"\b(?:que (?:puedes|puede|sabes) hacer|en que (?:puedes|puede) ayudarme)\b", normalized)
        if not capability:
            chosen = {}
    chunks = [c for c in load_lexical_corpus() if c.metadata.get("source_path", "").endswith(FAQ_PATH.name)]
    if not chosen:
        passages = retrieve_documents(question, documents=chunks, allowed_areas={"faq"}, limit=limit)
    else:
        topics = sorted(chosen, key=lambda topic: (min(words.index(cue) for cue in chosen[topic]), topic))
        queues = []
        for topic in topics:
            sections = {"Tarifas y cotizaciones"} if topic == "cotizaciones" else _FAQ_TOPICS[topic][1]
            for section in sorted(sections):
                selected = [c for c in chunks if c.metadata.get("section") == section]
                queues.append(retrieve_documents(section, documents=selected, allowed_areas={"faq"}, limit=limit))
        # Cubrir primero cada tema solicitado antes de añadir más de uno.
        passages = []
        seen = set()
        for offset in range(limit):
            for queue in queues:
                if offset < len(queue):
                    passage = queue[offset]
                    key = (passage.source_id, passage.content_digest)
                    if key not in seen:
                        passages.append(passage)
                        seen.add(key)
                        if len(passages) == limit:
                            break
            if len(passages) == limit:
                break
    context = "\n\n".join(f"[Fuente FAQ: {p.source_path}]\n{p.content}" for p in passages)
    return {"context": context, "contexts": [f"[Fuente FAQ: {p.source_path}]\n{p.content}" for p in passages], "source_ids": [p.source_id for p in passages], "state": None, "retrieval_query": question, "selected_sections": [p.section for p in passages]}


def prepare_candidate_case(sample):
    if sample["route"] == "faq":
        return retrieve_candidate_faq(sample["user_input"])
    from langchain_core.messages import HumanMessage
    from rag_eval.runtime import prepare_case
    query = prepare_query(sample["user_input"])
    result = prepare_case({**sample, "user_input": query})
    # La pregunta original queda intacta para cualquier generación posterior.
    result["state"]["messages"] = [HumanMessage(content=sample["user_input"])]
    result["state"]["failure_description"] = sample["user_input"]
    result["retrieval_query"] = query
    return result