"""Graph-neutral node for the unsupported supplier procurement flow."""
from typing import Any

from langchain_core.messages import AIMessage

from app.application.procurement import supplier_purchase_unavailable


def procurement_node(_state: dict[str, Any]) -> dict[str, Any]:
    result = supplier_purchase_unavailable()
    return {
        "current_agent": "compras",
        "outcome": result.outcome,
        "messages": [AIMessage(content=result.message)],
    }
