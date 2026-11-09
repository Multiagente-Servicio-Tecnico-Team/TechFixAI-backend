from datetime import date

import pytest

from app.domain.purchases import (
    PurchaseValidationFailure,
    PurchaseConflictFailure,
    ensure_invoice_receipt_allowed,
    validate_invoice_order_line_mapping,
    validate_invoice_order_supplier,
    validate_purchase,
)


def purchase_values(*, order_id=None, order_item_id=None):
    return {
        "supplier_id": 7,
        "purchase_order_id": order_id,
        "document_type": "FACTURA",
        "document_number": "F001-17",
        "issue_date": date(2026, 11, 9),
        "payment_method": "TRANSFER",
        "payment_status": "PENDING",
        "items": [{
            "spare_part_id": 4,
            "purchase_order_item_id": order_item_id,
            "description": "Memoria DDR4",
            "quantity": "2",
            "unit_cost": "45.50",
        }],
    }


def test_invoice_order_line_mapping_requires_order_header():
    with pytest.raises(PurchaseValidationFailure) as error:
        validate_purchase(purchase_values(order_item_id=12))
    assert error.value.field == "items.0.purchase_order_item_id"


def test_invoice_can_explicitly_map_line_to_linked_order():
    purchase = validate_purchase(purchase_values(order_id=31, order_item_id=12))
    assert purchase.purchase_order_id == 31
    assert purchase.lines[0].purchase_order_item_id == 12


def test_invoice_order_supplier_must_match():
    with pytest.raises(PurchaseValidationFailure):
        validate_invoice_order_supplier(31, 7, 9)
    validate_invoice_order_supplier(31, 7, 7)


def test_invoice_order_line_must_belong_to_header_order_and_match_part():
    with pytest.raises(PurchaseValidationFailure):
        validate_invoice_order_line_mapping(
            purchase_order_id=31, order_item_id=12, item_order_id=32,
            invoice_spare_part_id=4, order_spare_part_id=4,
        )
    with pytest.raises(PurchaseValidationFailure):
        validate_invoice_order_line_mapping(
            purchase_order_id=31, order_item_id=12, item_order_id=31,
            invoice_spare_part_id=4, order_spare_part_id=5,
        )


def test_invoice_linked_to_order_cannot_create_a_second_receipt():
    with pytest.raises(PurchaseConflictFailure, match=r"purchase-orders/\{order_id\}/receipts"):
        ensure_invoice_receipt_allowed(31)
    ensure_invoice_receipt_allowed(None)
