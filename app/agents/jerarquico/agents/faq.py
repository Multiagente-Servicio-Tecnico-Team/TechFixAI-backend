from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage, HumanMessage

from app.agents.jerarquico.graph.state import ServiceState
from app.rag.faq import FAQ_PATH, MarkdownFaqRetriever, answer_faq


def make_faq_agent(llm: Any, retriever: MarkdownFaqRetriever):
    def faq_agent(state: ServiceState) -> dict[str, Any]:
        question = next(
            (
                message.content
                for message in reversed(state["messages"])
                if isinstance(message, HumanMessage)
                and isinstance(message.content, str)
                and message.content.strip()
            ),
            "",
        )
        question = str(question)
        context = retriever.retrieve(question)
        response = answer_faq(llm, question, context)
        return {
            "route": "informational",
            "faq_context": context,
            "messages": [AIMessage(content=response)],
        }

    return faq_agent
