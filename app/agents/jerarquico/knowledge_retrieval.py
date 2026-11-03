from typing import Any

from app.agents.jerarquico.graph.state import ServiceState
from app.agents.jerarquico.retriever import MarkdownKnowledgeRetriever


def make_knowledge_retrieval_agent(
    retriever: MarkdownKnowledgeRetriever,
):
    def knowledge_retrieval_agent(state: ServiceState) -> dict[str, Any]:
        documents = retriever.retrieve(
            f"{state['title']} {state['failure_description']}",
            limit=3,
        )
        return {
            "rag_documents": retriever.as_state(documents),
            "rag_context": retriever.format_context(documents),
        }

    return knowledge_retrieval_agent
