"""Ejecuta componentes RAG existentes sin tickets, sesión ni persistencia."""
from __future__ import annotations

import re


def prepare_case(sample):
    from langchain_core.messages import HumanMessage
    if sample["route"] == "faq":
        from app.rag.faq import MarkdownFaqRetriever
        context = MarkdownFaqRetriever().retrieve(sample["user_input"], limit=3)
        contexts = re.split(r"\n\n(?=\[Fuente FAQ:)", context) if context else []
        return {"context": context, "contexts": contexts, "source_ids": [], "state": None}
    from app.agents.jerarquico.knowledge_retrieval import make_knowledge_retrieval_agent
    from app.agents.jerarquico.retriever import MarkdownKnowledgeRetriever
    state = {"title": "", "failure_description": sample["user_input"], "messages": [HumanMessage(content=sample["user_input"])]}
    state.update(make_knowledge_retrieval_agent(MarkdownKnowledgeRetriever())(state))
    context = state["rag_context"] if state["rag_documents"] else ""
    contexts = re.split(r"\n\n(?=Caso )", context) if context else []
    return {"context": context, "contexts": contexts, "source_ids": [d["id"] for d in state["rag_documents"]], "state": state}


def generate_case(sample, prepared, model):
    if sample["route"] == "faq":
        from app.rag.faq import answer_faq
        return answer_faq(model, sample["user_input"], prepared["context"]), None
    if not prepared["contexts"]:
        return None, None
    from app.agents.jerarquico.technical_support import make_technical_support_agent
    diagnosis = make_technical_support_agent(model, mode=sample["mode"])(prepared["state"])
    return diagnosis["provisional_diagnosis"], diagnosis