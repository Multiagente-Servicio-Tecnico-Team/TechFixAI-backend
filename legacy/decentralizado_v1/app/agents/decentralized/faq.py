"""Agente FAQ independiente del patrón Descentralizado."""
from langchain_core.messages import AIMessage

from app.config import create_chat_model
from app.agents.decentralized.policy import latest_user_message
from app.rag.faq import FAQ_ABSTENTION, MarkdownFaqRetriever, answer_faq


_FAQ_RETRIEVER = MarkdownFaqRetriever()
_LLM = create_chat_model()


def faq_node(state):
    """Responde preguntas informativas desde el FAQ canónico compartido."""
    question = latest_user_message(state)
    try:
        context = _FAQ_RETRIEVER.retrieve(question, limit=3)
    except Exception:
        context = ""

    try:
        response = answer_faq(_LLM, question, context)
    except Exception:
        if context.strip():
            excerpt = " ".join(
                line.strip()
                for line in context.splitlines()
                if line.strip() and not line.startswith("[Fuente FAQ:")
            )[:650]
            response = "Según la información disponible: " + excerpt
        else:
            response = FAQ_ABSTENTION

    return {
        "current_agent": "faq",
        "messages": [AIMessage(content=response)],
    }
