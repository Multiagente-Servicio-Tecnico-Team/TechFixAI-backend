"""Recorridos de Compras con nodos y herramientas reales, servicios simulados."""
import pytest
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from test_software_e2e import network, run, edges, call


@pytest.mark.parametrize("stock", [0, 3])
def test_faltante_almacen_compras_ventas(network, stock):
    _, controls = network
    controls["inventory_stock"] = stock
    result = run(network, "Consultar pieza", "almacen", request_revision=2,
                 required_parts=[{"name": "SSD de prueba", "quantity": 4}],
                 supplier_offers=[{"status": "QUOTE_CONFIRMED", "unit_cost": "1.00"}])
    assert edges(result) == [("almacen", "compras"), ("compras", "ventas")]
    assert result["out_of_stock_items"][0]["quantity"] == 4 - stock
    assert result["supplier_offers"][0]["status"] == "PRICE_UNAVAILABLE"
    assert result["quote"]["total"] is None
    assert all(part["available"] is False for part in result["quote"]["parts"])
    assert "No hay pedido" in result["messages"][-1].content
    assert not result.get("purchase_order_id") and result["inventory_requested_by"] is None
    assert controls["inventory_calls"] == [("SSD de prueba", 4)]


def test_faltante_completo_reutilizado_mismo_destino(network):
    _, controls = network
    result = run(network, "Consultar pieza", "almacen", request_revision=2, inventory_revision=2,
                 required_parts=[{"name": "SSD de prueba", "quantity": 1}],
                 inventory_results=[{"requested_name": "SSD de prueba", "name": "SSD de prueba", "quantity": 1,
                                     "stock": 0, "unit_price": "180.00", "available": False, "found": True, "tool_call_id": "old"}])
    assert edges(result) == [("almacen", "compras"), ("compras", "ventas")]
    assert controls["inventory_calls"] == []


def test_hardware_faltante_compras_ventas(network):
    _, controls = network
    controls["inventory_stock"] = 0
    controls["handlers"]["tecnico"] = lambda messages: call("transferir_a_almacen", motivo="Verificar pieza", nombre_repuesto="SSD de prueba", cantidad=1)
    result = run(network, "Quiero reemplazar el SSD de prueba", "tecnico")
    assert edges(result) == [("tecnico", "almacen"), ("almacen", "compras"), ("compras", "ventas")]


def test_compras_checkpoint_y_revision_obsoleta(network):
    module, _ = network
    graph = module.build_graph(checkpointer=MemorySaver())
    config = {"configurable": {"thread_id": "compras-a"}, "recursion_limit": 100}
    state = {"current_agent": "compras", "request_revision": 2, "inventory_revision": 2,
             "messages": [HumanMessage(content="Consultar faltante")],
             "required_parts": [{"name": "SSD de prueba", "quantity": 1}],
             "inventory_results": [{"requested_name": "SSD de prueba", "name": "SSD de prueba", "quantity": 1,
                                     "stock": 0, "unit_price": "180.00", "available": False, "found": True, "tool_call_id": "old"}]}
    first = graph.invoke(state, config)
    assert edges(first) == [("compras", "ventas")]
    second = graph.invoke({"messages": [HumanMessage(content="Continúa")], "current_agent": "compras", "request_revision": 3}, config)
    assert second["supplier_offers"] == [] and second["out_of_stock_items"] == []
    assert edges(second) == []
    assert second["messages"][:len(first["messages"])] == first["messages"]


@pytest.mark.parametrize("stock,available", [(0, True), (3, False)])
def test_cache_contradictorio_no_habilita_transferencia(network, stock, available):
    _, controls = network
    result = run(network, "Consultar pieza", "almacen", request_revision=2, inventory_revision=2,
                 required_parts=[{"name": "SSD de prueba", "quantity": 1}],
                 inventory_results=[{"requested_name": "SSD de prueba", "name": "SSD de prueba", "quantity": 1,
                                     "stock": stock, "available": available, "found": True,
                                     "unit_price": "180.00", "tool_call_id": "old"}])
    assert edges(result) == [] and result["current_agent"] == "almacen"
    assert not result.get("quote") and not controls["inventory_calls"]
    assert "identificación" in result["messages"][-1].content


@pytest.mark.parametrize("ambiguous", [False, True])
def test_varios_articulos_faltante_y_segunda_referencia(network, ambiguous):
    result = run(network, "Consultar piezas", "almacen", request_revision=2, inventory_revision=2,
                 required_parts=[{"name": "SSD de prueba", "quantity": 4}, {"name": "RAM de prueba", "quantity": 1}],
                 inventory_results=[
                     {"requested_name": "SSD de prueba", "name": "SSD de prueba", "quantity": 4,
                      "stock": 3, "available": False, "found": True, "unit_price": "180.00", "tool_call_id": "ssd"},
                     {"requested_name": "RAM de prueba", "name": "RAM de prueba", "quantity": 1,
                      "stock": 0 if ambiguous else 3, "available": not ambiguous, "found": not ambiguous,
                      "match_status": "ambiguous" if ambiguous else "exact", "unit_price": "150.00", "tool_call_id": "ram"}])
    if ambiguous:
        assert edges(result) == [] and not result.get("quote")
    else:
        assert edges(result) == [("almacen", "compras"), ("compras", "ventas")]
        assert result["out_of_stock_items"] == [{"name": "SSD de prueba", "quantity": 1}]
        assert result["quote"]["known_parts_subtotal"] == "150.00" and result["quote"]["total"] is None
