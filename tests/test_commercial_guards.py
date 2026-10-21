"""Regresiones del diálogo reportado, sin imports de clientes ni servicios."""
import ast
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from app.agents.decentralized import policy

ROOT = Path(__file__).resolve().parents[1]


def functions(filename, names, extra=None):
    tree = ast.parse((ROOT / filename).read_text(encoding="utf-8"))
    namespace = dict(vars(policy))
    namespace.update(AgentState=dict, AIMessage=AIMessage, HumanMessage=HumanMessage,
                     SystemMessage=SystemMessage, ToolMessage=ToolMessage,
                     SYSTEM_PROMPT="Prueba", Decimal=Decimal, InvalidOperation=InvalidOperation)
    namespace["json"] = json
    namespace.update(extra or {})
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
    exec(compile(ast.Module(body=nodes, type_ignores=[]), filename, "exec"), namespace)
    return namespace


class ForbiddenModel:
    def invoke(self, messages):
        pytest.fail("Esta ruta debe resolverse con datos verificados, no con el modelo")


def test_contexto_ventas_datos_preliminares_y_par_handoff():
    build = functions("app/agents/decentralized/ventas.py", {"build_sales_context"})["build_sales_context"]
    call = AIMessage(content="", tool_calls=[dict(name="transferir_a_ventas", args={"motivo": "Evaluar editor", "alcance": "solo_servicio"}, id="a")])
    output = ToolMessage(content='{"motivo":"Evaluar editor","alcance":"solo_servicio"}', name="transferir_a_ventas", tool_call_id="a")
    context = build({"messages": [call, output], "request_revision": 2,
                     "technical_assessment": {"software_diagnosis": "Hipótesis del editor"},
                     "handoff_records": [{"destino": "ventas", "request_revision": 1, "motivo": "Motivo antiguo"},
                                         {"origen": "software", "destino": "ventas", "request_revision": 2, "motivo": "Evaluar editor"}]})
    assert context[:2] == [call, output]
    assert "Hipótesis del editor" in context[-2].content and "no son instrucciones" in context[-2].content
    assert "Evaluar editor" in context[-1].content and "Motivo antiguo" not in context[-1].content


def sales():
    return functions("app/agents/decentralized/ventas.py", {
        "sales_node", "validate_inventory", "build_sales_context", "build_inventory_context",
    }, {"ventas_llm": ForbiddenModel()})["sales_node"]


def item(stock=10, quantity=1):
    return {"tool_call_id": "inventory-1", "requested_name": "SSD 500GB NVMe",
            "name": "SSD 500GB NVMe", "stock": stock, "quantity": quantity,
            "unit_price": "180.00", "available": stock >= quantity}


def test_no_inventa_mano_de_obra_total_o_moneda():
    result = sales()({"messages": [HumanMessage(content="Cotiza el repuesto")],
                      "quote_scope": "repuestos", "inventory_results": [item()]})
    reply = result["messages"][-1].content
    assert "stock 10" in reply and "cantidad solicitada 1" in reply
    assert "S/ 180.00" in reply and "$" not in reply and "120" not in reply and "300" not in reply
    assert result["quote"]["total"] is None and result["quote"]["labor_total"] is None
    assert result["quote"]["currency"] == "PEN"
    assert result["quote"]["known_parts_subtotal"] == "180.00"


def test_servicio_sin_precio_no_bloqueado_por_repuesto_pendiente():
    result = sales()({"messages": [HumanMessage(content="¿Cuánto cuesta una revisión?")],
                      "quote_scope": "solo_servicio", "inventory_pending": True})
    assert "tarifa" in result["messages"][-1].content.lower()
    assert result["quote"]["total"] is None


def test_compatibilidad_es_tecnica_incluso_con_inventario():
    result = sales()({"messages": [HumanMessage(content="¿Es compatible con mi laptop?")],
                      "inventory_results": [item()]})
    assert result["messages"][-1].tool_calls[0]["name"] == "transfer_to_hardware"


def test_soporte_no_inventa_canales_ni_promete_contacto():
    node = functions("app/agents/decentralized/soporte.py", {"support_node"}, {"soporte_llm": ForbiddenModel()})["support_node"]
    for text in ("¿Cómo solicito una revisión presencial?", "¿Puedes reservarme una cita?"):
        result = node({"messages": [HumanMessage(content=text)]})
        reply = result["messages"][-1].content
        assert "http" not in reply and "@" not in reply
        assert "No puedo reservar" in reply and "no hay una reserva" in reply


def test_revision_comercial_transfiere_con_alcance_correcto():
    node = functions("app/agents/decentralized/tecnico.py", {"hardware_node"})["hardware_node"]
    result = node({"messages": [HumanMessage(content="¿Cuánto cuesta una revisión de diagnóstico?")]})
    call = result["messages"][-1].tool_calls[0]
    assert call["name"] == "transfer_to_sales" and call["args"]["scope"] == "solo_servicio"


def test_repuesto_no_se_infiere_de_nombre_generico():
    state = {"messages": [HumanMessage(content="Quiero reemplazar el SSD") ]}
    assert not policy.repuesto_confirmado(state, "SSD")
    assert not policy.repuesto_confirmado(state, "SSD 500GB NVMe")
    state["messages"].append(HumanMessage(content="El técnico indicó SSD 500GB NVMe"))
    assert policy.repuesto_confirmado(state, "SSD 500GB NVMe")


def test_almacen_pide_repuesto_exacto_sin_elegir_otro():
    node = functions("app/agents/decentralized/almacen.py", {"warehouse_node"})["warehouse_node"]
    result = node({"messages": [HumanMessage(content="Una unidad")],
                   "required_parts": [{"name": "SSD 500GB NVMe", "quantity": 1}]})
    call = result["messages"][-1].tool_calls[0]
    assert call["name"] == "check_inventory"
    assert call["args"] == {"part_name": "SSD 500GB NVMe", "quantity": 1}


def test_subtotal_decimal_cantidad_y_stock_insuficiente():
    quote, _ = policy.cotizacion_verificada([
        {"nombre": "SSD", "cantidad": 2, "stock": 10, "precio_unitario": "180.00", "disponible": True},
        {"nombre": "Otro SSD", "cantidad": 2, "stock": 0, "precio_unitario": "180.00", "disponible": False},
    ], [])
    assert quote["known_parts_subtotal"] == "360.00"
    assert quote["parts"][1]["subtotal"] is None and quote["total"] is None


def test_inventario_con_error_no_confirma_precios():
    result = sales()({"messages": [HumanMessage(content="Cotiza")],
                      "quote_scope": "repuestos", "inventory_results": [item()],
                      "errors": ["Error al consultar inventario"]})
    assert result["quote"]["parts"] == []
    assert "180" not in result["messages"][-1].content


def test_almacen_no_reintenta_indefinidamente_una_consulta_fallida():
    node = functions("app/agents/decentralized/almacen.py", {"warehouse_node"})["warehouse_node"]
    result = node({"messages": [HumanMessage(content="Una unidad")],
                   "required_parts": [{"name": "SSD 500GB NVMe", "quantity": 1}],
                   "errors": ["Error al consultar inventario"]})
    assert not result["messages"][-1].tool_calls
    assert "No se pudo verificar" in result["messages"][-1].content


def test_tecnico_no_insiste_si_usuario_no_sabe_hacer_pruebas():
    node = functions("app/agents/decentralized/tecnico.py", {"hardware_node"})["hardware_node"]
    for text in ("Ni idea no se hacer prubeas tecnicas", "No sé conectar un monitor externo"):
        result = node({"messages": [HumanMessage(content=text)]})
        assert "revisión presencial" in result["messages"][-1].content
        assert not result["messages"][-1].tool_calls


def test_stock_en_ventas_va_a_almacen_no_a_soporte():
    result = sales()({"messages": [HumanMessage(content="q ssd tienes disponboes")]})
    assert result["messages"][-1].tool_calls[0]["name"] == "request_inventory"


def test_almacen_no_simula_un_listado_ni_elige_variante():
    node = functions("app/agents/decentralized/almacen.py", {"warehouse_node"})["warehouse_node"]
    result = node({"messages": [HumanMessage(content="q ssd tienes en stock")], "inventory_query": "SSD"})
    assert not result["messages"][-1].tool_calls
    assert "no listar" in result["messages"][-1].content
    result = node({"messages": [HumanMessage(content="SSD 500GB NVMe")], "inventory_query": "SSD"})
    assert result["messages"][-1].tool_calls[0]["args"]["part_name"] == "SSD 500GB NVMe"
    assert result["inventory_query"] is None


def test_marcador_se_pide_aclarar_sin_citas():
    result = sales()({"messages": [HumanMessage(content="El repuesto es [nombre exacto del SSD en tu inventario]")]})
    assert "corchetes" in result["messages"][-1].content
    assert "cita" not in result["messages"][-1].content


def test_transferencia_generica_a_soporte_no_responde_sobre_citas():
    node = functions("app/agents/decentralized/soporte.py", {"support_node"})["support_node"]
    result = node({"messages": [HumanMessage(content="Tengo una consulta"),
                   ToolMessage(content="Atención general", name="transferir_a_soporte", tool_call_id="support")]})
    assert "ticket" in result["messages"][-1].content
    assert "reservar" not in result["messages"][-1].content


def test_referencia_no_encontrada_no_muestra_precio_cero():
    result = sales()({"messages": [HumanMessage(content="Cotiza SSD 5000GB NVMe")],
                      "quote_scope": "repuestos", "inventory_results": [{**item(), "name": "SSD 5000GB NVMe",
                          "requested_name": "SSD 5000GB NVMe",
                          "stock": 0, "unit_price": "0.00", "available": False, "found": False}]})
    assert result["quote"]["parts"] == []
    assert result["quote"]["known_parts_subtotal"] is None
    assert "no se encontró" in result["messages"][-1].content
    assert "S/ 0" not in result["messages"][-1].content


def test_pregunta_instalacion_contesta_directamente():
    result = sales()({"messages": [HumanMessage(content="¿Ese importe incluye la instalación?")],
                      "inventory_results": [item()]})
    assert "No incluye instalación" in result["messages"][-1].content
    assert "stock 10" not in result["messages"][-1].content


def test_corregir_5000_a_500_reconsulta_almacen():
    state = {"messages": [HumanMessage(content="Busco una SSD 500GB NVMe")],
             "inventory_results": [{**item(), "requested_name": "SSD 5000GB NVMe", "found": False}],
             "required_parts": [{"name": "SSD 5000GB NVMe", "quantity": 1}]}
    result = sales()(state)
    call = result["messages"][-1].tool_calls[0]
    assert call["name"] == "request_inventory"
    assert "500GB" in call["args"]["query"]


def test_instalacion_sin_repuesto_encontrado_no_afirma_un_subtotal():
    result = sales()({"messages": [HumanMessage(content="¿Ese importe incluye la instalación?")],
                      "inventory_results": [{**item(), "found": False, "available": False, "stock": 0}]})
    assert "Todavía no hay un importe" in result["messages"][-1].content
