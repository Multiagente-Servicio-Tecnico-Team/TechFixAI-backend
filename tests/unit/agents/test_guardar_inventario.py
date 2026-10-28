
import json

from langchain_core.messages import ToolMessage
from app.agents.decentralized.graph import guardar_inventario


# =========================================================
# FUNCIÓN AUXILIAR
# =========================================================

def crear_mensaje(resultado, status="success"):
    return ToolMessage(
        content=json.dumps(resultado),
        name="consultar_inventario",
        tool_call_id="test-1",
        status=status,
    )


# =========================================================
# PRUEBA 1: INVENTARIO DISPONIBLE
# =========================================================

def test_guardar_inventario_disponible():
    resultado = {
        "requested_name": "RAM",
        "name": "Memoria RAM",
        "quantity": 2,
        "stock": 5,
        "unit_price": "120.00",
        "available": True,
    }

    state = {
        "messages": [crear_mensaje(resultado)],
        "inventory_results": [],
    }

    nuevo_estado = guardar_inventario(state)

    assert len(nuevo_estado["inventory_results"]) == 1

    guardado = nuevo_estado["inventory_results"][0]

    assert guardado["tool_call_id"] == "test-1"

    for campo, valor in resultado.items():
        assert guardado[campo] == valor


# =========================================================
# PRUEBA 2: REPUESTO SIN STOCK
# =========================================================

def test_guardar_inventario_sin_stock():
    resultado = {
        "requested_name": "RAM",
        "name": "Memoria RAM",
        "quantity": 2,
        "stock": 0,
        "unit_price": "120.00",
        "available": False,
    }

    state = {
        "messages": [crear_mensaje(resultado)],
    }

    nuevo_estado = guardar_inventario(state)

    assert (
        nuevo_estado["inventory_results"][0]["available"]
        is False
    )


# =========================================================
# PRUEBA 3: ERROR DE INVENTARIO
# =========================================================

def test_guardar_inventario_error():
    mensaje = ToolMessage(
        content="Error de conexión",
        name="consultar_inventario",
        tool_call_id="test-1",
        status="error",
    )

    state = {
        "messages": [mensaje],
    }

    nuevo_estado = guardar_inventario(state)

    assert nuevo_estado["inventory_results"] == []
    assert (
        "Error al consultar inventario"
        in nuevo_estado["errors"]
    )


# =========================================================
# PRUEBA 4: JSON INVÁLIDO
# =========================================================

def test_guardar_inventario_json_invalido():
    mensaje = ToolMessage(
        content="Esto no es JSON",
        name="consultar_inventario",
        tool_call_id="test-1",
    )

    state = {
        "messages": [mensaje],
    }

    nuevo_estado = guardar_inventario(state)

    assert nuevo_estado["inventory_results"] == []
    assert (
        "Resultado de inventario inválido"
        in nuevo_estado["errors"]
    )


# =========================================================
# PRUEBA 5: EVITAR RESULTADOS DUPLICADOS
# =========================================================

def test_guardar_inventario_sin_duplicados():
    resultado = {
        "requested_name": "RAM",
        "name": "Memoria RAM",
        "quantity": 2,
        "stock": 5,
        "unit_price": "120.00",
        "available": True,
    }

    mensaje = crear_mensaje(resultado)

    state = {
        "messages": [mensaje],
        "inventory_results": [],
    }

    primera = guardar_inventario(state)

    segunda = guardar_inventario({
        "messages": [mensaje],
        "inventory_results": primera["inventory_results"],
    })

    assert len(segunda["inventory_results"]) == 1
