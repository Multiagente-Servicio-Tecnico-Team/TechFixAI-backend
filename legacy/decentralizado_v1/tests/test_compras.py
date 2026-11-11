"""Política y herramientas consultivas sin servicios ni escrituras."""
import pytest
from langchain_core.messages import HumanMessage, ToolMessage
from app.agents.decentralized.policy import evaluar_abastecimiento
from app.agents.decentralized.compras import compras_node
from app.agents.decentralized.tools.compras_tools import consultar_fuentes_abastecimiento, transferir_a_ventas
from app.agents.decentralized.tools.almacen_tools import transferir_a_compras
from app.agents.decentralized.handoffs import HANDOFF_TOOLS, handoff_reason


def value(stock=3, quantity=4, **result_changes):
    return {"request_revision": 2, "inventory_revision": 2,
            "required_parts": [{"name": "SSD de prueba", "quantity": quantity}],
            "inventory_results": [{"requested_name": "SSD de prueba", "name": "SSD de prueba",
                                   "quantity": quantity, "stock": stock, "available": stock >= quantity,
                                   "found": True, "unit_price": "180.00", **result_changes}],
            "messages": [HumanMessage(content="Consultar SSD de prueba")]}


@pytest.mark.parametrize("stock,quantity,status,destination,missing", [
    (3, 1, "AVAILABLE", "ventas", 0), (3, 4, "PARTIAL", "compras", 1),
    (0, 1, "OUT_OF_STOCK", "compras", 1),
])
def test_stock_confirmado(stock, quantity, status, destination, missing):
    result = evaluar_abastecimiento(value(stock, quantity))
    assert result["destination"] == destination
    assert result["inventory_checks"][0]["status"] == status
    assert result["inventory_checks"][0]["missing_quantity"] == missing


@pytest.mark.parametrize("kind,status", [("ambiguous", "NEEDS_DETAILS"), ("not_found", "NOT_FOUND")])
def test_ausencia_no_es_stock_agotado(kind, status):
    result = evaluar_abastecimiento(value(0, 1, found=False, match_status=kind))
    assert result["destination"] is None and result["out_of_stock_items"] == []
    assert result["inventory_checks"][0]["status"] == status


@pytest.mark.parametrize("change", [{"inventory_revision": 1}, {"inventory_results": []}, {"errors": ["Error al consultar inventario"]}])
def test_error_o_revision_obsoleta_no_habilita_compras(change):
    state = value(); state.update(change)
    assert evaluar_abastecimiento(state)["destination"] is None
    result = compras_node(state)
    assert not result["messages"][0].tool_calls and result["supplier_offers"] == []


def test_capacidades_y_ofertas_sin_inventar_datos():
    assert consultar_fuentes_abastecimiento.invoke({})["integration_available"] is False
    state = value()
    first = compras_node(state)
    assert first["messages"][0].tool_calls[0]["name"] == "get_sourcing_capabilities"
    state["messages"].append(ToolMessage(content='{"integration_available":false}', name="consultar_fuentes_abastecimiento", tool_call_id="a"))
    result = compras_node(state)
    assert result["messages"][0].tool_calls[0]["name"] == "transfer_to_sales"
    offer = result["supplier_offers"][0]
    assert offer["status"] == "PRICE_UNAVAILABLE" and offer["request"]["quantity"] == 1
    assert not {"supplier_id", "unit_cost", "delivery_lead_days", "purchase_order_id"} & offer.keys()


@pytest.mark.parametrize("tool,destination", [(transferir_a_compras, "compras"), (transferir_a_ventas, "ventas")])
def test_handoff_compatible(tool, destination):
    assert HANDOFF_TOOLS[tool.name] == destination
    output = tool.invoke({"motivo": " Faltante verificado "})
    assert handoff_reason([ToolMessage(content=output, name=tool.name, tool_call_id="a")]) == "Faltante verificado"
    with pytest.raises(ValueError):
        tool.invoke({"motivo": " "})


@pytest.mark.parametrize("changes", [
    {"stock": 0, "available": True}, {"stock": 2, "available": True},
    {"stock": 4, "available": False}, {"stock": None}, {"stock": -1},
    {"stock": True}, {"stock": "3"}, {"stock": 3.0},
    {"available": 1}, {"available": "false"},
    {"found": None}, {"found": 1}, {"name": " "},
    {"found": True, "match_status": "ambiguous"},
    {"quantity": True},
])
def test_inventario_inconsistente_no_transfiere(changes):
    state = value(); state["inventory_results"][0].update(changes)
    result = evaluar_abastecimiento(state)
    assert result["destination"] is None and result["out_of_stock_items"] == []
    assert result["inventory_checks"][0]["status"] == "NEEDS_DETAILS"


def test_stock_ausente_no_confirma_disponibilidad():
    state = value(); state["inventory_results"][0].pop("stock")
    assert evaluar_abastecimiento(state)["destination"] is None


@pytest.mark.parametrize("quantity", [0, -1, True, False, "4", 4.0, None])
def test_cantidad_solicitada_invalida(quantity):
    state = value(); state["required_parts"][0]["quantity"] = quantity
    state["inventory_results"][0]["quantity"] = quantity
    assert evaluar_abastecimiento(state)["destination"] is None


@pytest.mark.parametrize("ambiguous", [False, True])
def test_varios_articulos_y_referencia_ambigua(ambiguous):
    state = value()
    part = {"name": "RAM de prueba", "quantity": 1}
    state["required_parts"].append(part)
    state["inventory_results"].append({"requested_name": part["name"], "name": part["name"],
                                        "quantity": 1, "stock": 3, "found": not ambiguous,
                                        "available": not ambiguous, "match_status": "ambiguous" if ambiguous else "exact"})
    result = evaluar_abastecimiento(state)
    assert result["destination"] == (None if ambiguous else "compras")
    assert result["out_of_stock_items"] == [{"name": "SSD de prueba", "quantity": 1}]


def test_utf8_archivo_y_mensaje():
    from pathlib import Path
    from app.agents.decentralized.policy import salida_abastecimiento
    content = (Path(__file__).resolve().parents[1] / "app/agents/decentralized/policy.py").read_bytes().decode("utf-8")
    assert "identificaci?n" not in content and "ambig?edad" not in content
    message = salida_abastecimiento({})["messages"][0].content
    assert "identificación" in message and "ambigüedad" in message
