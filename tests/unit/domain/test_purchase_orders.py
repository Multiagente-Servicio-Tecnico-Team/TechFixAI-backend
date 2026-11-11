from decimal import Decimal

import pytest

from app.domain.purchase_orders import (
    PurchaseOrderConflictFailure,
    PurchaseOrderValidationFailure,
    transition_order_status,
    validate_order_receipt,
    validate_order_receipt_quantities,
    next_order_receipt_status,
    validate_purchase_order,
)


def draft_values():
    return {
        "supplier_id": 7,
        "estimated_arrival": None,
        "notes": "Necesario esta semana",
        "items": [
            {"spare_part_id": 4, "description": "Memoria DDR4", "quantity": 2, "unit_cost": "45.50"},
            {"spare_part_id": None, "description": "Servicio de embalaje", "quantity": 1, "unit_cost": "5.00"},
        ],
    }


def test_order_calculates_exact_totals_from_lines():
    draft = validate_purchase_order(draft_values())
    assert draft.total_amount == Decimal("96.00")
    assert [line.subtotal for line in draft.items] == [Decimal("91.00"), Decimal("5.00")]
    assert draft.items[0].quantity == 2


@pytest.mark.parametrize("supplier_id", [0, -1, True, "7"])
def test_order_requires_positive_integer_supplier_id(supplier_id):
    values = draft_values()
    values["supplier_id"] = supplier_id
    with pytest.raises(PurchaseOrderValidationFailure) as error:
        validate_purchase_order(values)
    assert error.value.field == "supplier_id"


@pytest.mark.parametrize("quantity", [0, -1, True, 1.5, "2"])
def test_order_quantity_must_be_positive_integer(quantity):
    values = draft_values()
    values["items"][0]["quantity"] = quantity
    with pytest.raises(PurchaseOrderValidationFailure) as error:
        validate_purchase_order(values)
    assert error.value.field == "items.0.quantity"


@pytest.mark.parametrize("unit_cost", ["-1.00", "1.001", "nan", "1000000000000.00"])
def test_order_cost_must_be_exact_non_negative_money(unit_cost):
    values = draft_values()
    values["items"][0]["unit_cost"] = unit_cost
    with pytest.raises(PurchaseOrderValidationFailure) as error:
        validate_purchase_order(values)
    assert error.value.field == "items.0.unit_cost"


def test_order_requires_at_least_one_line_and_description():
    values = draft_values()
    values["items"] = []
    with pytest.raises(PurchaseOrderValidationFailure):
        validate_purchase_order(values)
    values = draft_values()
    values["items"][1]["description"] = "   "
    with pytest.raises(PurchaseOrderValidationFailure) as error:
        validate_purchase_order(values)
    assert error.value.field == "items.1.description"


def test_issue_transitions_only_a_draft_to_issued():
    assert transition_order_status("DRAFT", "ISSUE") == "ISSUED"
    for status in ("ISSUED", "PARTIALLY_RECEIVED", "RECEIVED", "CANCELLED"):
        with pytest.raises(PurchaseOrderConflictFailure):
            transition_order_status(status, "ISSUE")


@pytest.mark.parametrize("status", ["DRAFT", "ISSUED", "PARTIALLY_RECEIVED"])
def test_cancel_preserves_received_history_from_allowed_states(status):
    assert transition_order_status(status, "CANCEL", reason="Proveedor canceló") == "CANCELLED"


@pytest.mark.parametrize("status", ["RECEIVED", "CANCELLED"])
def test_cancel_rejects_terminal_states(status):
    with pytest.raises(PurchaseOrderConflictFailure):
        transition_order_status(status, "CANCEL", reason="No procede")


def test_cancel_requires_a_bounded_reason():
    with pytest.raises(PurchaseOrderValidationFailure) as missing:
        transition_order_status("DRAFT", "CANCEL", reason=" ")
    assert missing.value.field == "reason"
    with pytest.raises(PurchaseOrderValidationFailure):
        transition_order_status("DRAFT", "CANCEL", reason="x" * 501)


def test_receipt_requires_positive_integer_quantities_and_unique_lines():
    with pytest.raises(PurchaseOrderValidationFailure):
        validate_order_receipt({"items": [{"purchase_order_item_id": 1, "quantity_received": 0}]})
    with pytest.raises(PurchaseOrderValidationFailure):
        validate_order_receipt({"items": [
            {"purchase_order_item_id": 1, "quantity_received": 1},
            {"purchase_order_item_id": 1, "quantity_received": 1},
        ]})


def test_receipt_hash_is_normalized_for_item_order_and_notes_whitespace():
    first = validate_order_receipt({"items": [
        {"purchase_order_item_id": 2, "quantity_received": 4},
        {"purchase_order_item_id": 1, "quantity_received": 1},
    ], "notes": "  bultos completos  "})
    second = validate_order_receipt({"items": [
        {"purchase_order_item_id": 1, "quantity_received": 1},
        {"purchase_order_item_id": 2, "quantity_received": 4},
    ], "notes": "bultos completos"})
    assert first.request_hash == second.request_hash


def test_receipt_rejects_over_receipt_and_calculates_partial_then_received_status():
    ordered = {1: 10, 2: 2}
    already = {1: 4, 2: 0}
    with pytest.raises(PurchaseOrderConflictFailure):
        validate_order_receipt_quantities(ordered, already, {1: 7})
    partial = validate_order_receipt_quantities(ordered, already, {1: 6})
    assert next_order_receipt_status("ISSUED", ordered, partial) == "PARTIALLY_RECEIVED"
    complete = validate_order_receipt_quantities(ordered, partial, {2: 2})
    assert next_order_receipt_status("PARTIALLY_RECEIVED", ordered, complete) == "RECEIVED"
