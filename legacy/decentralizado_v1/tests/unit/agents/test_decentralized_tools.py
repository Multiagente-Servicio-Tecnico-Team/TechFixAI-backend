import pytest
from decimal import Decimal
from langchain_core.messages import HumanMessage

from app.agents.decentralized.tools.soporte_tools import (
    consultar_estado_ticket,
    transferir_a_tecnico as soporte_a_tecnico,
    transferir_a_ventas as soporte_a_ventas,
)

from app.agents.decentralized.tools.tecnico_tools import (
    diagnosticar_problema,
    transferir_a_ventas as tecnico_a_ventas,
)

from app.agents.decentralized.tools.ventas_tools import (
    generar_cotizacion,
    transferir_a_tecnico as ventas_a_tecnico,
)


def test_ticket_existente_se_limita_a_cliente_autenticado(monkeypatch):
    import app.agents.decentralized.tools.soporte_tools as tools

    class Repository:
        def list_customer_tickets(self, customer_id):
            assert customer_id == 41
            return [{"code": "TCK-84", "status": "OPEN"}]

    monkeypatch.setattr(tools, "ticket_repository", Repository())
    resultado = consultar_estado_ticket.invoke(
        {"ticket_code": "tck-84", "state": {"customer_id": 41}}
    )
    assert "TCK-84" in resultado
    assert "OPEN" in resultado


def test_ticket_inexistente_no_revela_tickets_de_otros_clientes(monkeypatch):
    import app.agents.decentralized.tools.soporte_tools as tools

    class Repository:
        def list_customer_tickets(self, customer_id):
            assert customer_id == 41
            return []

    monkeypatch.setattr(tools, "ticket_repository", Repository())
    resultado = consultar_estado_ticket.invoke(
        {"ticket_code": "TCK-99", "state": {"customer_id": 41}}
    )
    assert "No encontré" in resultado

# PRUEBA 3: DIAGNÃ“STICOS CONOCIDOS
@pytest.mark.parametrize(
    "sintoma, esperado",
    [
        ("Mi PC no enciende", "fuente"),
        ("Mi PC se apaga", "temperatura"),
        ("Tengo pantalla azul", "memoria RAM"),
        ("Mi equipo esta lento", "recursos"),
    ],
)
def test_diagnosticos(sintoma, esperado):
    resultado = diagnosticar_problema.invoke(
        {"sintoma": sintoma}
    )
    assert esperado.lower() in resultado.lower()


# PRUEBA 4: DIAGNÃ“STICO DESCONOCIDO
def test_diagnostico_desconocido():
    resultado = diagnosticar_problema.invoke(
        {"sintoma": "Problema desconocido"}
    )
    assert "No se encontró" in resultado


# PRUEBA 5: NORMALIZACIÃ“N
def test_diagnostico_normalizacion():
    resultado = diagnosticar_problema.invoke(
        {"sintoma": "  MI PC NO ENCIENDE  "}
    )
    assert "fuente" in resultado.lower()


def test_cotizacion_usa_catalogo_compartido_y_contexto_autenticado(monkeypatch):
    from app.application.catalog import CatalogService
    from app.settings import Settings
    import app.agents.decentralized.tools.ventas_tools as ventas_tools

    class Repository:
        def find_spare_part_by_code(self, code):
            assert code == "SSD-512"
            return {
                "id": 7, "code": code, "name": "SSD 512GB",
                "category": "Almacenamiento", "unit_price": Decimal("35.50"),
                "current_stock": 3,
            }

        def lookup_inventory(self, name, quantity):
            raise AssertionError("La cotización usa bÃºsqueda por cÃ³digo explÃ­cito")

        def find_spare_parts(self, term): return []
        def find_catalog_items(self, term, *, limit=20): return []
        def find_spare_part_alternatives(self, term): return []

    settings = Settings(
        groq_api_key="test", groq_model="test", database_url="test",
        langsmith_api_key=None, langsmith_tracing=False,
        langsmith_project="test", langsmith_hide_inputs=True,
        langsmith_hide_outputs=True,
        labor_maintenance_price=Decimal("20.00"),
        labor_diagnosis_price=Decimal("15.00"),
    )
    monkeypatch.setattr(ventas_tools, "catalog_service", CatalogService(Repository()))
    monkeypatch.setattr(ventas_tools, "load_settings", lambda: settings)

    quote = generar_cotizacion.invoke({
        "parts": [{"code": "SSD-512", "quantity": 1}],
        "state": {
            "customer_id": 41, "conversation_id": "conversation-1",
            "quote_type": "REPAIR", "quote_task_type": "maintenance",
        },
    })

    assert quote["total_amount"] == Decimal("55.50")
    assert quote["parts"][0]["unit_price"] == Decimal("35.50")
    assert quote["labor_cost"] == Decimal("20.00")
    assert "state" not in generar_cotizacion.tool_call_schema.model_json_schema()["properties"]


def test_ventas_usa_el_calculador_compartido_para_inventario_verificado(monkeypatch):
    from app.application.catalog import CatalogService
    from app.settings import Settings
    from app.agents.decentralized import ventas
    from app.agents.decentralized.ventas import ventas_node
    import app.agents.decentralized.tools.ventas_tools as ventas_tools

    class Repository:
        def find_spare_part_by_code(self, code):
            assert code == "SSD-512"
            return {
                "id": 7, "code": code, "name": "SSD 512GB",
                "category": "Almacenamiento", "unit_price": Decimal("35.50"),
                "current_stock": 3,
            }

        def lookup_inventory(self, name, quantity): raise AssertionError
        def find_spare_parts(self, term): return []
        def find_catalog_items(self, term, *, limit=20): return []
        def find_spare_part_alternatives(self, term): return []
        def create_intake_ticket(self, **values): return 84

    settings = Settings(
        groq_api_key="test", groq_model="test", database_url="test",
        langsmith_api_key=None, langsmith_tracing=False,
        langsmith_project="test", langsmith_hide_inputs=True,
        langsmith_hide_outputs=True,
        labor_maintenance_price=Decimal("20.00"),
        labor_diagnosis_price=Decimal("15.00"),
    )
    monkeypatch.setattr(ventas_tools, "catalog_service", CatalogService(Repository()))
    monkeypatch.setattr(ventas_tools, "load_settings", lambda: settings)
    monkeypatch.setattr(ventas, "load_settings", lambda: settings)
    monkeypatch.setattr(ventas, "sales_repository", Repository(), raising=False)
    result = ventas_node({
        "customer_id": 41,
        "conversation_id": "conversation-1",
        "ticket_id": 84,
        "ticket_code": "TCK-84",
        "request_type": "REPAIR",
        "quote_type": "REPAIR",
        "quote_task_type": "maintenance",
        "quote_scope": "repuestos",
        "request_revision": 0,
        "inventory_revision": 0,
        "inventory_pending": False,
        "inventory_results": [{
            "tool_call_id": "inventory-1", "requested_name": "SSD 512GB",
            "inventory_id": 7, "name": "SSD 512GB", "quantity": 1, "stock": 3,
            "unit_price": "35.50", "code": "SSD-512", "found": True,
            "available": True,
        }],
        "required_parts": [{"name": "SSD 512GB", "quantity": 1}], "errors": [],
        "messages": [HumanMessage(content="Cotiza el componente revisado")],
    })

    assert Decimal(result["quote"]["total"]) == Decimal("55.50")
    assert result["quote_status"] == "PENDING"
    assert "S/ 55.50" in result["messages"][0].content


@pytest.mark.parametrize("decision", ["confirmo", "rechazo"])
def test_ventas_resuelve_confirmacion_explicita_de_cotizacion(decision):
    from app.agents.decentralized.sales import sales_node

    class Writer:
        def __init__(self): self.calls = []
        def accept_ticket_quote(self, **values):
            self.calls.append(values)
            return {"quote_id": 93, "payment_id": 94, "payment_code": "PAY-TEST",
                    "payment_status": "PENDING"}

    writer = Writer()
    state = {
        "customer_id": 41, "ticket_id": 84, "ticket_code": "TCK-84",
        "request_type": "REPAIR", "quote_task_type": "maintenance",
        "quote_status": "PENDING",
        "quote": {"status": "proposed", "labor_task_type": "maintenance",
                  "labor_total": "35.00", "known_parts_subtotal": "20.00",
                  "total": "55.00", "parts": [{"inventory_id": 17, "quantity": 1,
                  "unit_price": "20.00", "subtotal": "20.00", "available": True}]},
        "messages": [HumanMessage(content=decision)],
    }
    result = sales_node(state, authenticated_customer_id=41, service_quote_repository=writer)
    if decision == "confirmo":
        assert result["quote_status"] == "ACCEPTED"
        assert result["quote_id"] == 93 and result["payment_id"] == 94
        assert writer.calls[0]["customer_id"] == 41 and writer.calls[0]["ticket_id"] == 84
    else:
        assert result["quote_status"] == "REJECTED"
        assert writer.calls == []
def test_ventas_pide_nueva_confirmacion_si_cambio_precio():
    from app.agents.decentralized.sales import sales_node
    from app.domain.errors import StaleQuote

    class Writer:
        def accept_ticket_quote(self, **_values): raise StaleQuote("live price changed")

    result = sales_node({
        "customer_id": 41, "request_type": "REPAIR", "ticket_id": 84,
        "quote_status": "PENDING", "quote_task_type": "maintenance",
        "quote": {"status": "proposed", "labor_task_type": "maintenance",
                  "labor_total": "35.00", "known_parts_subtotal": "20.00",
                  "total": "55.00", "parts": [{"inventory_id": 17, "quantity": 1,
                  "unit_price": "20.00", "subtotal": "20.00", "available": True}]},
        "messages": [HumanMessage(content="confirmo")],
    }, authenticated_customer_id=41, service_quote_repository=Writer())
    assert result.get("quote_id") is None
    assert result["quote"]["status"] == "incomplete"
    assert "registr" in result["messages"][0].content.lower()
def test_ventas_no_duplica_una_cotizacion_ya_aceptada():
    from app.agents.decentralized.sales import sales_node
    result = sales_node({
        "quote_id": 93, "quote_status": "ACCEPTED", "payment_code": "PAY-TEST",
        "quote": {"total": "55.50", "status": "confirmed"},
        "messages": [HumanMessage(content="confirmo")],
    })
    assert result["quote_status"] == "ACCEPTED"
    assert "cotización ya fue aceptada" in result["messages"][0].content.lower()
    assert "pago sigue pendiente" in result["messages"][0].content.lower()
def test_ventas_mantiene_cotizacion_pendiente_si_respuesta_es_ambigua():
    from app.agents.decentralized.sales import sales_node
    result = sales_node({
        "customer_id": 41, "request_type": "REPAIR", "ticket_id": 84,
        "quote_status": "PENDING", "quote_task_type": "maintenance",
        "quote": {"status": "proposed", "total": "55.50", "labor_total": "35.00",
                  "known_parts_subtotal": "20.00", "parts": []},
        "messages": [HumanMessage(content="Lo voy a revisar")],
    })
    assert result["quote_status"] == "PENDING"
    assert "sigue pendiente" in result["messages"][0].content.lower()
def test_ventas_rechaza_aceptacion_si_el_stock_cambio():
    from app.agents.decentralized.sales import sales_node
    from app.domain.errors import StaleQuote

    class Writer:
        def accept_ticket_quote(self, **_values): raise StaleQuote("stock changed")

    result = sales_node({
        "customer_id": 41, "request_type": "REPAIR", "ticket_id": 84,
        "quote_status": "PENDING", "quote_task_type": "maintenance",
        "quote": {"status": "proposed", "labor_task_type": "maintenance",
                  "labor_total": "35.00", "known_parts_subtotal": "20.00",
                  "total": "55.00", "parts": [{"inventory_id": 17, "quantity": 1,
                  "unit_price": "20.00", "subtotal": "20.00", "available": True}]},
        "messages": [HumanMessage(content="confirmo")],
    }, authenticated_customer_id=41, service_quote_repository=Writer())
    assert result.get("quote_id") is None
    assert result["quote"]["status"] == "incomplete"
    assert "registr" in result["messages"][0].content.lower()
def test_cotizacion_rechaza_tipo_de_trabajo_no_validado():
    with pytest.raises(ValueError, match="tipo de cotizaci"):
        generar_cotizacion.invoke({
            "parts": [],
            "state": {
                "customer_id": 41, "conversation_id": "conversation-1",
                "quote_task_type": "free",
            },
        })


def test_cotizacion_requiere_identidad_autenticada():
    with pytest.raises(PermissionError, match="autenticada"):
        generar_cotizacion.invoke({
            "parts": [],
            "state": {
                "conversation_id": "conversation-1",
                "quote_type": "DIRECT_SALE",
                "quote_task_type": "sale",
            },
        })


# PRUEBA 9: HANDOFFS DE SOPORTE
def test_handoffs_soporte():
    tecnico = soporte_a_tecnico.invoke(
        {"motivo": "Falla de hardware"}
    )
    ventas = soporte_a_ventas.invoke(
        {"motivo": "Solicita precio"}
    )

    assert tecnico == "TRANSFERIR_TECNICO: Falla de hardware"
    assert ventas == "TRANSFERIR_VENTAS: Solicita precio"


# PRUEBA 10: HANDOFFS DE TÃ‰CNICO Y VENTAS
def test_handoffs_otros_agentes():
    ventas = tecnico_a_ventas.invoke(
        {"motivo": "Necesita cotización", "alcance": "solo_servicio"}
    )
    tecnico = ventas_a_tecnico.invoke(
        {"motivo": "Necesita diagnóstico"}
    )

    assert ventas == {
        "accion": "SOLICITAR_COTIZACION",
        "motivo": "Necesita cotización",
        "alcance": "solo_servicio",
        "nombre_repuesto": "",
        "cantidad": 1,
    }
    assert tecnico == "TRANSFERIR_TECNICO: Necesita diagnóstico"
