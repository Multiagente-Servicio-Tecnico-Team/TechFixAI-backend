
from app.agents.decentralized.ventas import (
    validar_inventario,
    construir_contexto_inventario,
)


def crear_resultado(
    cantidad=2,
    stock=5,
    precio="120.00",
    disponible=True,
):
    return {
        "tool_call_id": "consulta-1",
        "requested_name": "RAM",
        "name": "Memoria RAM",
        "quantity": cantidad,
        "stock": stock,
        "unit_price": precio,
        "available": disponible,
    }


# 1. Inventario disponible
def test_inventario_disponible():
    state = {
        "inventory_results": [crear_resultado()]
    }

    inventario, errores = validar_inventario(state)

    assert errores == []
    assert len(inventario) == 1
    assert inventario[0]["subtotal"] == "240.00"
    assert inventario[0]["disponible"] is True


# 2. Stock insuficiente
def test_stock_insuficiente():
    state = {
        "inventory_results": [
            crear_resultado(
                cantidad=8,
                stock=5,
                disponible=False,
            )
        ]
    }

    inventario, errores = validar_inventario(state)

    assert errores == []
    assert inventario[0]["disponible"] is False
    assert inventario[0]["subtotal"] is None


def test_contexto_repuesto_sin_stock():
    state = {
        "inventory_results": [
            crear_resultado(
                cantidad=8,
                stock=5,
                disponible=False,
            )
        ],
    }

    contexto = construir_contexto_inventario(state)

    assert '"disponible": false' in contexto.content
    assert '"subtotal": null' in contexto.content

# 3. Precio negativo
def test_precio_negativo():
    state = {
        "inventory_results": [
            crear_resultado(precio="-20.00")
        ]
    }

    inventario, errores = validar_inventario(state)

    assert inventario == []
    assert len(errores) == 1


# 4. Cantidad inválida
def test_cantidad_invalida():
    state = {
        "inventory_results": [
            crear_resultado(cantidad=0)
        ]
    }

    inventario, errores = validar_inventario(state)

    assert inventario == []
    assert len(errores) == 1


# 5. Stock inconsistente
def test_disponibilidad_inconsistente():
    state = {
        "inventory_results": [
            crear_resultado(
                cantidad=8,
                stock=5,
                disponible=True,
            )
        ]
    }

    inventario, errores = validar_inventario(state)

    assert inventario == []
    assert len(errores) == 1


# 6. Consulta duplicada
def test_consulta_duplicada():
    resultado = crear_resultado()

    state = {
        "inventory_results": [
            resultado,
            resultado.copy(),
        ]
    }

    inventario, errores = validar_inventario(state)

    assert errores == []
    assert len(inventario) == 1


# 7. Error de inventario
def test_error_inventario():
    state = {
        "inventory_results": [],
        "errors": ["Error al consultar inventario"],
    }

    contexto = construir_contexto_inventario(state)

    assert "ERROR" in contexto.content
    assert "No confirmes precios" in contexto.content


# 8. Inventario vacío
def test_inventario_vacio():
    state = {
        "inventory_results": [],
    }

    contexto = construir_contexto_inventario(state)

    assert "No existen resultados" in contexto.content
