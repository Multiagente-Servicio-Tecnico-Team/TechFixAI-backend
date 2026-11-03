"""Isolated schema compatibility tests; no graph, LLM or database is used."""
from copy import deepcopy
from decimal import Decimal

import pytest

from app.agents.decentralized.data_compat import (
    DataCompatibilityError,
    normalize_handoff_history_entry,
    normalize_handoff_payload,
    normalize_handoff_record,
    normalize_inventory_result,
    normalize_sales_inventory_item,
)


SCHEMAS = [
    (normalize_handoff_history_entry,
     {"origen": "software", "destino": "tecnico"},
     {"origin": "software", "destination": "tecnico"}),
    (normalize_handoff_record,
     {"origen": "almacen", "destino": "compras", "motivo": "Faltantes confirmados",
      "request_revision": 2, "progress_token": "existing-token"},
     {"origin": "almacen", "destination": "compras", "reason": "Faltantes confirmados",
      "request_revision": 2, "progress_token": "existing-token"}),
    (normalize_handoff_payload,
     {"accion": "SOLICITAR_COTIZACION", "motivo": "Evaluar servicio",
      "alcance": "solo_servicio", "nombre_repuesto": "", "cantidad": 1},
     {"action": "SOLICITAR_COTIZACION", "reason": "Evaluar servicio",
      "scope": "solo_servicio", "part_name": "", "quantity": 1}),
    (normalize_sales_inventory_item,
     {"encontrado": False, "nombre": "SSD solicitado", "cantidad": 2,
      "stock": 0, "precio_unitario": "0.00", "disponible": False, "subtotal": None},
     {"found": False, "name": "SSD solicitado", "quantity": 2,
      "stock": 0, "unit_price": "0.00", "available": False, "subtotal": None}),
    (normalize_inventory_result,
     {"requested_name": "SSD solicitado", "name": "SSD identificado", "quantity": 2,
      "stock": 1, "unit_price": Decimal("180.00"), "available": False,
      "found": True, "inventory_id": 7, "tool_call_id": "call-1"},
     {"requested_name": "SSD solicitado", "name": "SSD identificado", "quantity": 2,
      "stock": 1, "unit_price": Decimal("180.00"), "available": False,
      "found": True, "inventory_id": 7, "tool_call_id": "call-1"}),
]


@pytest.mark.parametrize("normalize,legacy,canonical", SCHEMAS)
@pytest.mark.parametrize("format_name", ["legacy", "canonical", "mixed"])
def test_recognized_formats(normalize, legacy, canonical, format_name):
    source = {"legacy": legacy, "canonical": canonical,
              "mixed": {**legacy, **canonical}}[format_name]
    assert normalize(source) == canonical


@pytest.mark.parametrize("normalize,legacy,canonical", SCHEMAS)
def test_no_mutation_metadata_and_idempotence(normalize, legacy, canonical):
    source = {**legacy, "metadata": {"origen": "external", "items": [{"cantidad": 3}]}}
    original = deepcopy(source)
    result = normalize(source)
    assert source == original
    assert result == {**canonical, "metadata": original["metadata"]}
    assert normalize(result) == result
    assert result is not source
    result["metadata"]["items"][0]["cantidad"] = 99
    assert source == original


@pytest.mark.parametrize("normalize,legacy,canonical", SCHEMAS)
def test_missing_fields_are_not_completed(normalize, legacy, canonical):
    assert normalize({}) == {}
    assert normalize({"metadata": None}) == {"metadata": None}


@pytest.mark.parametrize("normalize,legacy,canonical", SCHEMAS)
@pytest.mark.parametrize("source", [None, [], "{}", 1, True, {1: "value"}])
def test_malformed_container(normalize, legacy, canonical, source):
    with pytest.raises(TypeError):
        normalize(source)


ALIASES = [
    (normalize_handoff_history_entry, "origen", "origin"),
    (normalize_handoff_history_entry, "destino", "destination"),
    (normalize_handoff_record, "origen", "origin"),
    (normalize_handoff_record, "destino", "destination"),
    (normalize_handoff_record, "motivo", "reason"),
    (normalize_handoff_payload, "accion", "action"),
    (normalize_handoff_payload, "motivo", "reason"),
    (normalize_handoff_payload, "alcance", "scope"),
    (normalize_handoff_payload, "nombre_repuesto", "part_name"),
    (normalize_handoff_payload, "cantidad", "quantity"),
    (normalize_handoff_payload, "consulta", "query"),
    (normalize_sales_inventory_item, "encontrado", "found"),
    (normalize_sales_inventory_item, "nombre", "name"),
    (normalize_sales_inventory_item, "cantidad", "quantity"),
    (normalize_sales_inventory_item, "precio_unitario", "unit_price"),
    (normalize_sales_inventory_item, "disponible", "available"),
]


@pytest.mark.parametrize("normalize,legacy,canonical", ALIASES)
def test_conflicting_aliases_leave_input_untouched(normalize, legacy, canonical):
    source = {legacy: "first", canonical: "second", "metadata": [1]}
    original = deepcopy(source)
    with pytest.raises(DataCompatibilityError):
        normalize(source)
    assert source == original


@pytest.mark.parametrize("left,right", [
    (True, 1), (False, 0), (1, 1.0), (Decimal("1"), 1),
    ("1", 1), ([True], [1]), ({"value": True}, {"value": 1}),
    ([1], (1,)), ({True: "value"}, {1: "value"}),
])
def test_conflict_comparison_is_type_sensitive(left, right):
    with pytest.raises(DataCompatibilityError):
        normalize_handoff_payload({"cantidad": left, "quantity": right})


def test_equal_nested_aliases_ignore_dictionary_order():
    value = {"a": [1, {"value": False}], "b": None}
    assert normalize_handoff_payload({"motivo": value, "reason": dict(reversed(list(value.items())))}) == {"reason": value}


def test_only_keys_for_the_selected_schema_are_normalized():
    data = {"motivo": "metadata", "nombre": "metadata", "cantidad": 1}
    assert normalize_handoff_history_entry(data) == data
    assert normalize_inventory_result(data) == data
    assert normalize_handoff_record(data) == {
        "reason": "metadata", "nombre": "metadata", "cantidad": 1,
    }


@pytest.mark.parametrize("action", [
    "TRANSFERIR_ALMACEN", "SOLICITAR_COTIZACION", "CONSULTAR_DISPONIBILIDAD",
])
def test_action_values_and_query_are_preserved(action):
    assert normalize_handoff_payload({"accion": action, "consulta": "SSD de 500 GB"}) == {
        "action": action, "query": "SSD de 500 GB",
    }


@pytest.mark.parametrize("scope", ["solo_servicio", "repuestos", "sin_determinar"])
def test_scope_values_and_tool_identifiers_are_preserved(scope):
    data = {"alcance": scope, "name": "transferir_a_ventas", "tool_call_id": "existing-id"}
    assert normalize_handoff_payload(data) == {
        "scope": scope, "name": "transferir_a_ventas", "tool_call_id": "existing-id",
    }


def test_absent_fields_and_explicit_null_are_distinct():
    assert normalize_handoff_record({"request_revision": None}) == {"request_revision": None}
    assert normalize_handoff_record({"motivo": None}) == {"reason": None}
    with pytest.raises(DataCompatibilityError):
        normalize_handoff_record({"motivo": None, "reason": ""})


def test_adapter_does_not_certify_inventory_or_complete_a_request():
    source = {"cantidad": 0, "disponible": True}
    assert normalize_sales_inventory_item(source) == {"quantity": 0, "available": True}
    result = normalize_inventory_result({"found": False, "match_status": "ambiguous"})
    assert result == {"found": False, "match_status": "ambiguous"}
    assert "stock" not in result and "unit_price" not in result


def test_conflict_error_does_not_include_values_or_metadata():
    with pytest.raises(DataCompatibilityError) as caught:
        normalize_handoff_record({"motivo": "private-a", "reason": "private-b",
                                  "metadata": "private-c"})
    assert all(value not in str(caught.value) for value in ("private-a", "private-b", "private-c"))
