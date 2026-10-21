from decimal import Decimal
from unittest.mock import patch

import pytest

from app.agents.decentralized.tools.almacen_tools import (
    consultar_inventario,
)


@patch("app.agents.decentralized.tools.almacen_tools.lookup_inventory")
def test_inventario_disponible(mock_lookup):
    mock_lookup.return_value = {
        "name": "Memoria RAM 8GB",
        "quantity": 2,
        "stock": 5,
        "unit_price": Decimal("120.00"),
        "available": True,
    }

    resultado = consultar_inventario.invoke({
        "nombre_repuesto": "Memoria RAM 8GB",
        "cantidad": 2,
    })

    assert resultado["available"] is True
    assert resultado["stock"] == 5
    assert resultado["unit_price"] == "120.00"

    mock_lookup.assert_called_once_with(
        requested_name="Memoria RAM 8GB",
        quantity=2,
    )


@patch("app.agents.decentralized.tools.almacen_tools.lookup_inventory")
def test_inventario_sin_stock(mock_lookup):
    mock_lookup.return_value = {
        "name": "SSD 1TB",
        "quantity": 3,
        "stock": 1,
        "unit_price": Decimal("250.00"),
        "available": False,
    }

    resultado = consultar_inventario.invoke({
        "nombre_repuesto": "SSD 1TB",
        "cantidad": 3,
    })

    assert resultado["available"] is False
    assert resultado["stock"] == 1


def test_nombre_vacio():
    with pytest.raises(ValueError):
        consultar_inventario.invoke({
            "nombre_repuesto": "   ",
            "cantidad": 1,
        })


def test_cantidad_invalida():
    with pytest.raises(ValueError):
        consultar_inventario.invoke({
            "nombre_repuesto": "SSD",
            "cantidad": 0,
        })