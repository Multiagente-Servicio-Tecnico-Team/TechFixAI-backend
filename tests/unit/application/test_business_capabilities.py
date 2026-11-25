from decimal import Decimal

import pytest

from app.application.quotes import calculate_quote
from app.application.catalog import lookup_catalog_item


def test_shared_quote_calculation_uses_decimal_and_server_prices():
    quote = calculate_quote(
        labor_cost="35",
        labor_task_type="maintenance",
        parts=[{"id": 7, "name": "SSD", "quantity": 2, "unit_price": "12.35"}],
    )

    assert quote["parts_cost"] == Decimal("24.70")
    assert quote["total_amount"] == Decimal("59.70")
    assert quote["parts"][0]["subtotal"] == Decimal("24.70")


@pytest.mark.parametrize(
    "parts", [[{"quantity": True, "unit_price": "10"}], [{"quantity": 1, "unit_price": "0"}]]
)
def test_shared_quote_rejects_invalid_quantity_and_zero_item_price(parts):
    with pytest.raises(ValueError):
        calculate_quote(labor_cost="35", labor_task_type="maintenance", parts=parts)


def test_catalog_lookup_rejects_model_supplied_quantity_before_repository_call():
    calls = []

    def lookup(name, quantity):
        calls.append((name, quantity))
        return {"stock": 3, "available": True, "found": True, "unit_price": "10.00"}

    with pytest.raises(ValueError):
        lookup_catalog_item("SSD", True, lookup=lookup)
    assert calls == []


def test_catalog_lookup_uses_repository_values_and_validates_availability():
    result = lookup_catalog_item(
        " SSD ", 2,
        lookup=lambda name, quantity: {
            "name": name, "stock": 2, "available": True,
            "found": True, "unit_price": Decimal("12.5"),
        },
    )
    assert result["unit_price"] == "12.50"
    with pytest.raises(RuntimeError, match="inconsistente"):
        lookup_catalog_item(
            "SSD", 2,
            lookup=lambda *_: {"stock": 0, "available": True, "unit_price": "0"},
        )
