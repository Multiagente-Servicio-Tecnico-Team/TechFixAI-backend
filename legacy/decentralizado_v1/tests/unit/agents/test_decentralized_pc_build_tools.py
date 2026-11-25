from langchain_core.messages import HumanMessage

from app.agents.decentralized.graph import AGENT_NODES
from app.agents.decentralized.sales import _pc_build_option, _persist_pc_build_quote, sales_node
from app.agents.decentralized.support import support_node


def test_pc_build_intent_routes_to_the_active_sales_node():
    result = support_node({
        "messages": [HumanMessage(content="Quiero armar una PC gamer")],
    })

    call = result["messages"][0].tool_calls[0]
    assert call["name"] == "transfer_to_sales"
    assert AGENT_NODES["ventas"] is sales_node


def test_pc_build_quote_components_require_catalog_ids():
    option = {
        "code": "gaming-basic", "name": "PC gamer inicial",
        "labor_cost": "50.00", "total": "150.00",
        "compatibility_notes": "Compatibilidad final por validar.",
        "parts": [{
            "id": 90, "code": "RAM-32", "name": "RAM 32GB",
            "category": "RAM Desktop", "quantity": 1,
            "current_stock": 2, "unit_price": "100.00", "subtotal": "100.00",
        }],
    }

    prepared = _pc_build_option(option)

    assert prepared["parts"][0]["inventory_id"] == 90
    assert prepared["parts"][0]["stock"] == 2
    assert prepared["total"] == "150.00"


def test_pc_build_quote_uses_shared_ticketless_sales_quote_writer(monkeypatch):
    import app.application.chat_sales_quotes as chat_quotes

    calls = []
    monkeypatch.setattr(chat_quotes, "save_chat_sales_quote", lambda **values: calls.append(values) or {"id": 17})
    option = {
        "code": "gaming-basic", "name": "PC gamer inicial",
        "labor_cost": "50.00", "total": "150.00",
        "compatibility_notes": "Compatibilidad final por validar.",
        "parts": [{"inventory_id": 90, "name": "RAM 32GB", "code": "RAM-32",
                   "quantity": 1, "unit_price": "100.00", "subtotal": "100.00"}],
    }

    _persist_pc_build_quote(customer_id=41, option=option)

    assert calls[0]["customer_id"] == 41
    assert calls[0]["quote_type"] == "PC_BUILD"
    assert calls[0]["parts"][0]["inventory_id"] == 90
    assert "ticket_id" not in calls[0]
