"""Agente informativo del Orquestador sobre el corpus FAQ compartido."""
from langchain_core.messages import AIMessage, HumanMessage

from app.config import create_chat_model
from app.rag.faq import MarkdownFaqRetriever, answer_faq

_RETRIEVER = MarkdownFaqRetriever()


def faq_node(state: dict[str, object]) -> dict[str, object]:
    question = str(state.get("faq_query", "")).strip()
    if not question:
        question = next(
            (
                str(message.content).strip()
                for message in reversed(state.get("messages", []))
                if isinstance(message, HumanMessage)
                and isinstance(message.content, str)
                and message.content.strip()
            ),
            "",
        )
    context = _RETRIEVER.retrieve(question)
    response = answer_faq(create_chat_model(), question, context)
    return {
        "faq_pending": False,
        "faq_context": context,
        "response": response,
        "messages": [AIMessage(content=response)],
    }
