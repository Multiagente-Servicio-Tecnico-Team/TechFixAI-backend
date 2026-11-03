from decimal import Decimal
from unittest.mock import patch

import pytest
from langchain_core.messages import AIMessage
from langgraph.prebuilt import ToolNode
from langgraph.graph import END, START, StateGraph
from app.agents.decentralized.state import AgentState

from app.agents.decentralized.tools.almacen_tools import (
    consultar_inventario,
)


def invoke_inventory(name, quantity):
    return consultar_inventario.func(
        name,
        {"customer_id": 8, "conversation_id": "inventory-test"},
        quantity,
    )


@patch("app.agents.decentralized.tools.almacen_tools.catalog_service._repository.lookup_inventory")
def test_inventario_disponible(mock_lookup):
    mock_lookup.return_value = {
        "name": "Memoria RAM 8GB",
        "quantity": 2,
        "stock": 5,
        "unit_price": Decimal("120.00"),
        "available": True,
    }

    resultado = invoke_inventory("Memoria RAM 8GB", 2)

    assert resultado["available"] is True
    assert resultado["stock"] == 5
    assert resultado["unit_price"] == "120.00"

    mock_lookup.assert_called_once_with("Memoria RAM 8GB", 2)


@patch("app.agents.decentralized.tools.almacen_tools.catalog_service._repository.lookup_inventory")
def test_inventario_sin_stock(mock_lookup):
    mock_lookup.return_value = {
        "name": "SSD 1TB",
        "quantity": 3,
        "stock": 1,
        "unit_price": Decimal("250.00"),
        "available": False,
    }

    resultado = invoke_inventory("SSD 1TB", 3)

    assert resultado["available"] is False
    assert resultado["stock"] == 1


def test_nombre_vacio():
    with pytest.raises(ValueError):
        invoke_inventory("   ", 1)


def test_cantidad_invalida():
    with pytest.raises(ValueError):
        invoke_inventory("SSD", 0)


def test_identity_is_injected_by_graph_state_not_model_arguments():
    assert set(consultar_inventario.tool_call_schema.model_fields) == {
        "nombre_repuesto", "cantidad",
    }


@patch("app.agents.decentralized.tools.almacen_tools.catalog_service._repository.lookup_inventory")
def test_tool_node_injects_authenticated_customer_context(mock_lookup):
    mock_lookup.return_value = {
        "name": "SSD 1TB", "quantity": 1, "stock": 3,
        "unit_price": Decimal("250.00"), "available": True,
    }
    call = AIMessage(
        content="",
        tool_calls=[{
            "name": "consultar_inventario",
            "args": {"nombre_repuesto": "SSD 1TB", "cantidad": 1},
            "id": "catalog-call",
            "type": "tool_call",
        }],
    )

    builder = StateGraph(AgentState)
    builder.add_node("tools", ToolNode([consultar_inventario]))
    builder.add_edge(START, "tools")
    builder.add_edge("tools", END)
    graph = builder.compile()
    result = graph.invoke({
        "messages": [call],
        "customer_id": 8,
        "conversation_id": "tool-node-test",
    })

    assert result["messages"][-1].status == "success"
    assert "250.00" in result["messages"][-1].content
    mock_lookup.assert_called_once_with("SSD 1TB", 1)
