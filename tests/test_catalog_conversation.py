"""Grafo real y catálogo SQLite sintético; no certifica PostgreSQL ni modelos."""
from copy import deepcopy
from decimal import Decimal

import pytest
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from app.agents.decentralized import policy
from test_inventory_matching import inventory
from test_software_e2e import network, edges, pairs
from test_decentralized_quote_acceptance import quote_api, quote_database, quote_graph
from test_session_guard import env


@pytest.mark.parametrize("message,expected", [
    ("¿Tienen un SSD Samsung 970 EVO Plus de 500 GB?", "SSD Samsung 970 EVO Plus 500 GB"),
    ("Quiero comprar dos SSD de 500 GB", "SSD 500 GB"),
    ("¿Qué precio tiene RAM Kingston de 8 GB DDR4?", "RAM Kingston 8 GB DDR4"),
    ("SSD 500GB NVMe", "SSD 500GB NVMe"),
    ("SSD500GB", "SSD500GB"),
    ("Quiero un SSD de 5000GB SATA", "SSD 5000GB SATA"),
    ("[nombre del SSD 500GB]", None),
    ("Necesito una batería", None),
])
def test_natural_reference_preserves_reported_specs(message, expected):
    assert policy.extract_inventory_reference(message) == expected


@pytest.fixture
def catalog(inventory):
    lookup, _ = inventory
    engine = create_engine("sqlite://", poolclass=StaticPool,
                           connect_args={"check_same_thread": False})
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE spare_parts (id INTEGER PRIMARY KEY, code TEXT UNIQUE, name TEXT, current_stock INTEGER, unit_price NUMERIC, active BOOLEAN)"))
        connection.execute(text("INSERT INTO spare_parts VALUES (:id,:code,:name,:stock,:price,:active)"), [
            dict(id=1, code="SSD-A", name="SSD Samsung 970 EVO Plus 500GB NVMe", stock=4, price="180.10", active=True),
            dict(id=2, code="SSD-B", name="SSD Kingston 500GB NVMe", stock=2, price="150.20", active=True),
            dict(id=3, code="SSD-C", name="SSD Inactivo 500GB NVMe", stock=99, price="1.00", active=False),
        ])
    yield lookup, engine
    engine.dispose()


def test_catalog_options_never_select_first_or_include_inactive(catalog):
    lookup, engine = catalog
    result = lookup("SSD 500GB NVMe", 2, engine)
    assert result["found"] is False and result["available"] is False
    assert result["match_status"] == "ambiguous"
    assert {item["code"] for item in result["candidates"]} == {"SSD-A", "SSD-B"}
    assert lookup("SSD-A", 2, engine)["unit_price"] == Decimal("180.10")
    assert lookup("SSD 5000GB", 1, engine)["match_status"] == "not_found"


def test_options_are_not_quote_lines_and_preserve_input(catalog):
    lookup, engine = catalog
    item = lookup("SSD 500GB NVMe", 2, engine)
    before = deepcopy(item)
    quote, reply = policy.build_verified_quote([item], [])
    assert item == before
    assert quote["parts"] == [] and quote["total"] is None
    assert "SSD-A" in reply and "SSD-B" in reply and "180.10" in reply
    assert "código o nombre exacto" in reply


@pytest.mark.parametrize("patch", [
    {"unit_price": "NaN"}, {"unit_price": "-1"}, {"id": True},
    {"current_stock": -1}, {"current_stock": True}, {"name": ""},
    {"code": []}, {"code": ""},
])
def test_invalid_candidates_cannot_authorize_handoff(catalog, patch):
    lookup, engine = catalog
    item = lookup("SSD 500GB NVMe", 2, engine)
    item["candidates"][0].update(patch)
    state = dict(request_revision=1, inventory_revision=1, required_parts=[dict(name="SSD 500GB NVMe", quantity=2)], inventory_results=[item])
    assert policy.evaluate_supply(state)["destination"] is None


@pytest.mark.parametrize("stock,subtotal", [(3, "380.50"), (1, "0.00")])
def test_graph_options_selection_rechecks_stock_and_keeps_quantity(network, catalog, monkeypatch, stock, subtotal):
    module, controls = network
    lookup, engine = catalog
    import app.agents.decentralized.tools.warehouse_tools as tools
    queries = []
    def search(*, requested_name, quantity):
        queries.append((requested_name, quantity))
        return lookup(requested_name, quantity, engine)
    monkeypatch.setattr(tools, "lookup_inventory", search)
    graph = module.build_graph(checkpointer=MemorySaver())
    config = {"configurable": {"thread_id": "synthetic-catalog"}, "recursion_limit": 100}
    first = graph.invoke({"messages": [HumanMessage(content="¿Tienen stock de SSD 500GB NVMe?")],
                          "request_type": "SALE", "intake": {"product_description": "SSD 500GB NVMe", "quantity": 2}}, config)
    pairs(first)
    assert edges(first) == [("soporte", "ventas"), ("ventas", "almacen"), ("almacen", "ventas")]
    assert "SSD-A" in first["messages"][-1].content and "SSD-B" in first["messages"][-1].content
    assert not first.get("quote_id") and first["quote"]["parts"] == []
    with engine.begin() as connection:
        connection.execute(text("UPDATE spare_parts SET current_stock=:stock,unit_price=190.25 WHERE code='SSD-A'"), {"stock": stock})
    second = graph.invoke({"messages": [HumanMessage(content="Elijo SSD-A")]}, config)
    pairs(second)
    assert queries == [("SSD 500GB NVMe", 2), ("SSD-A", 2)]
    assert second["quote"]["known_parts_subtotal"] == subtotal
    assert second["quote"]["total"] == (subtotal if stock >= 2 else None) and not second.get("payment_id")
    assert not second.get("ticket_id") and not second.get("quote_id")
    with engine.connect() as connection:
        assert connection.execute(text("SELECT current_stock FROM spare_parts WHERE code='SSD-A'")).scalar_one() == stock


@pytest.mark.parametrize("message", ["No quiero SSD-A", "Quizás SSD-A", "Elijo SSD-A o SSD-B"])
def test_no_selection_from_negation_uncertainty_or_multiple_codes(catalog, message):
    lookup, engine = catalog
    state = dict(messages=[HumanMessage(content=message)], request_revision=1, inventory_revision=1,
                 required_parts=[dict(name="SSD 500GB NVMe", quantity=2)],
                 inventory_results=[lookup("SSD 500GB NVMe", 2, engine)])
    assert policy.selected_inventory_reference(state) is None


def test_stale_candidates_do_not_authorize_selection(catalog):
    lookup, engine = catalog
    state = dict(messages=[HumanMessage(content="Elijo SSD-A")], request_revision=2, inventory_revision=1,
                 required_parts=[dict(name="SSD 500GB NVMe", quantity=2)],
                 inventory_results=[lookup("SSD 500GB NVMe", 2, engine)])
    assert policy.selected_inventory_reference(state) is None


@pytest.mark.parametrize("request_type,labor,total", [("SALE", "0.00", "180.10"),
                                                   ("REPAIR", "35.00", "215.10"),
                                                   ("SUPPORT", "35.00", "215.10")])
def test_approved_labor_rates_do_not_confirm_commercial_operations(catalog, request_type, labor, total):
    lookup, engine = catalog
    item = lookup("SSD-A", 1, engine)
    quote, reply = policy.build_verified_quote([item], [], request_type=request_type)
    assert quote["labor_total"] == labor and quote["total"] == total
    assert quote["status"] == "proposed" and "no se ha registrado" in reply.lower()


def test_pc_build_rate_does_not_bypass_missing_components(catalog):
    lookup, engine = catalog
    quote, reply = policy.build_verified_quote([lookup("SSD-A", 1, engine)], [], request_type="PC_BUILD")
    assert quote["total"] is None and "50.00" in reply and "ocho componentes" in reply


@pytest.mark.parametrize("request_type", ["REPAIR", "SUPPORT"])
def test_service_only_quote_uses_approved_rate(request_type):
    quote, reply = policy.build_verified_quote([], [], scope="solo_servicio", request_type=request_type)
    assert quote["total"] == "35.00" and quote["parts"] == []
    assert "no se ha registrado" in reply.lower()


@pytest.mark.parametrize("patch", [{"errors": ["inventario inválido"]}, {"pending": True}])
def test_errors_or_pending_block_even_approved_prices(catalog, patch):
    lookup, engine = catalog
    values = dict(inventory=[lookup("SSD-A", 1, engine)], errors=[], request_type="SALE")
    quote, _ = policy.build_verified_quote(**{**values, **patch})
    assert quote["total"] is None


def test_generic_family_reads_catalog_without_selecting(network, catalog, monkeypatch):
    module, controls = network
    lookup, engine = catalog
    import app.agents.decentralized.tools.warehouse_tools as tools
    monkeypatch.setattr(tools, "lookup_inventory", lambda **kwargs: lookup(engine=engine, **kwargs))
    result = module.graph.invoke({"messages": [HumanMessage(content="¿Qué SSD tienen en stock?")]},
                                 config={"recursion_limit": 100})
    pairs(result)
    assert edges(result) == [("soporte", "ventas"), ("ventas", "almacen"), ("almacen", "ventas")]
    assert "SSD-A" in result["messages"][-1].content and "SSD-B" in result["messages"][-1].content
    assert not result.get("quote_id") and result["quote"]["total"] is None


@pytest.fixture
def identity_catalog(inventory):
    lookup, _ = inventory
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE spare_parts (id INTEGER PRIMARY KEY, code TEXT UNIQUE, name TEXT, category TEXT, description TEXT, current_stock INTEGER, unit_price NUMERIC, active BOOLEAN)"))
        connection.execute(text("INSERT INTO spare_parts VALUES (:id,:code,:name,:category,:description,4,:price,1)"), [
            dict(id=1, code="SSD-PRIMARY", name="SSD Samsung 500GB NVMe", category="Almacenamiento",
                 description="Incluye adaptador USB; compatible con RAM DDR4", price="180.10"),
            dict(id=2, code="ADAPTER-USB", name="Adaptador USB para SSD", category="Accesorios",
                 description="Compatible con SSD NVMe 500GB; no incluye SSD", price="10.20"),
            dict(id=3, code="ENCLOSURE-USB", name="Carcasa USB para SSD", category="Accesorios",
                 description="Compatible con SSD NVMe 500GB", price="20.30"),
            dict(id=4, code="MODEL-500", name="Modelo principal 500", category="SSD",
                 description="500 GB NVMe; no incluye adaptador USB", price="150.40"),
            dict(id=5, code="CLEAN-KIT", name="Kit limpieza", category="Accesorios",
                 description="No incluye SSD 500GB NVMe", price="5.50"),
        ])
    yield lookup, engine
    engine.dispose()


@pytest.mark.parametrize("query,expected", [
    ("SSD-PRIMARY", 1), ("ssd-primary", 1), ("ADAPTER-USB", 2),
    ("SSD Samsung 500GB NVMe", 1), ("Adaptador USB para SSD", 2),
    ("adaptador SSD 500GB NVMe", 2), ("carcasa SSD 500GB NVMe", 3),
    ("Modelo principal 500", 4),
])
def test_identity_lookup_preserves_codes_names_and_explicit_accessories(identity_catalog, query, expected):
    lookup, engine = identity_catalog
    result = lookup(query, 2, engine)
    assert result["found"] is True and result["inventory_id"] == expected
    assert result["quantity"] == 2 and result["stock"] == 4
    assert result["available"] is True and isinstance(result["unit_price"], Decimal)


def test_ssd_alternatives_exclude_accessories_and_preserve_descriptive_specs(identity_catalog):
    lookup, engine = identity_catalog
    result = lookup("SSD 500 GB NVMe", 2, engine)
    assert result["found"] is False and result["match_status"] == "ambiguous"
    assert {item["id"] for item in result["candidates"]} == {1, 4}
    assert {item["code"] for item in result["candidates"]} == {"SSD-PRIMARY", "MODEL-500"}
    assert lookup("MODEL-500", 2, engine)["unit_price"] == Decimal("150.40")


def test_accessories_alone_do_not_become_a_main_ssd_match(identity_catalog):
    lookup, engine = identity_catalog
    with engine.begin() as connection:
        connection.execute(text("DELETE FROM spare_parts WHERE id IN (1,4)"))
    result = lookup("SSD 500GB NVMe", 1, engine)
    assert result["found"] is False and result["match_status"] == "not_found"
    assert result["inventory_id"] is None and not result.get("candidates")


@pytest.mark.parametrize("description", [
    "No incluye SSD 500GB NVMe", "Sin SSD 500GB NVMe",
    "Compatible con SSD 500GB NVMe", "Soporta SSD 500GB NVMe",
])
def test_related_or_negative_mentions_are_not_product_identity(identity_catalog, description):
    lookup, engine = identity_catalog
    with engine.begin() as connection:
        connection.execute(text("DELETE FROM spare_parts WHERE id != 5"))
        connection.execute(text("UPDATE spare_parts SET description=:description"), dict(description=description))
    result = lookup("SSD 500GB NVMe", 1, engine)
    assert result["found"] is False and result["inventory_id"] is None


def test_product_mentions_of_accessories_do_not_replace_explicit_accessory(identity_catalog):
    lookup, engine = identity_catalog
    with engine.begin() as connection:
        connection.execute(text("UPDATE spare_parts SET name='SSD Samsung 500GB NVMe con adaptador USB' WHERE id=1"))
    assert lookup("adaptador USB", 1, engine)["inventory_id"] == 2
    result = lookup("SSD Samsung 500GB NVMe", 1, engine)
    assert result["inventory_id"] == 1 and result["unit_price"] == Decimal("180.10")


def test_explicit_accessory_category_preserves_catalog_search(identity_catalog):
    lookup, engine = identity_catalog
    result = lookup("Accesorios", 1, engine)
    assert result["found"] is False and result["match_status"] == "ambiguous"
    assert {item["id"] for item in result["candidates"]} == {2, 3, 5}


def test_positive_name_attributes_after_con_are_preserved(identity_catalog):
    lookup, engine = identity_catalog
    with engine.begin() as connection:
        connection.execute(text("UPDATE spare_parts SET name='SSD Samsung 500GB NVMe con disipador' WHERE id=1"))
    assert lookup("SSD Samsung 500GB NVMe disipador", 1, engine)["inventory_id"] == 1


@pytest.mark.parametrize("query", ["ADAPTER-USB", "adaptador SSD 500GB NVMe", "SSD 500GB NVMe"])
def test_orchestrator_inventory_consumer_keeps_its_contract(identity_catalog, monkeypatch, query):
    from app.agents.orquestador.tools import inventory as module
    lookup, engine = identity_catalog
    calls = []
    def search(requested_name, quantity):
        calls.append((requested_name, quantity))
        return lookup(requested_name, quantity, engine)
    monkeypatch.setattr(module, "lookup_inventory", search)
    schema = module.consultar_inventario.tool_call_schema.model_json_schema()
    assert set(schema["properties"]) == {"nombre_repuesto", "cantidad"}
    assert schema["required"] == ["nombre_repuesto"]
    expected = lookup(query, 2, engine)
    result = module.consultar_inventario.invoke(dict(nombre_repuesto=query, cantidad=2))
    assert result == {**expected, "unit_price": str(expected["unit_price"])}
    assert calls == [(query, 2)]


def test_catalog_produces_a_new_proposal_accepted_by_authenticated_http(quote_api):
    from test_decentralized_quote_acceptance import body
    client, value, _ = quote_api
    value.graph.update_state(value.config, {"proposal": None, "quote": {}}, as_node="ventas")
    preview = client.post("/api/chat", json=body(value, action=None, proposal_id=None, message="Cotiza los repuestos"))
    assert preview.status_code == 200
    proposal = preview.json()["quote"]
    assert proposal["status"] == "proposed" and proposal["total"] == "360.00"
    assert proposal["proposal_id"]
    accepted = client.post("/api/chat", json=body(value, proposal_id=proposal["proposal_id"]))
    assert accepted.status_code == 200 and accepted.json()["quote"]["status"] == "confirmed"
    assert accepted.json()["quote"]["proposal_id"] == proposal["proposal_id"]


