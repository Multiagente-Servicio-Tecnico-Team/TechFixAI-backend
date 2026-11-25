from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.adapters.tools.catalog import CatalogLookupInput
from app.adapters.tools.quotes import QuoteCalculationInput
from app.application.catalog import lookup_catalog_item


def test_model_cannot_supply_price_stock_or_availability():
    repository_result = {
        "requested_name": "SSD 512GB",
        "name": "SSD 512GB",
        "quantity": 1,
        "stock": 3,
        "unit_price": Decimal("35.50"),
        "available": True,
        "found": True,
    }
    observed = []

    result = lookup_catalog_item(
        "SSD 512GB",
        1,
        lookup=lambda name, quantity: (observed.append((name, quantity)) or repository_result),
    )

    assert observed == [("SSD 512GB", 1)]
    assert result["unit_price"] == "35.50"
    assert result["stock"] == 3 and result["available"] is True
    with pytest.raises(TypeError):
        lookup_catalog_item(
            "SSD 512GB",
            1,
            lookup=lambda *_: repository_result,
            unit_price=Decimal("0.01"),
        )


@pytest.mark.parametrize(
    "forged_fields",
    [
        {"customer_id": 999},
        {"unit_price": "0.01"},
        {"stock": 999, "available": True},
        {"parts_cost": "0.01", "total_amount": "0.01"},
        {"status": "ACCEPTED"},
    ],
)
def test_strict_quote_tool_schema_rejects_model_supplied_authoritative_values(
    forged_fields,
):
    arguments = {
        "parts": [{"code": "SSD-512", "quantity": 1}],
        **forged_fields,
    }

    with pytest.raises(ValidationError):
        QuoteCalculationInput.model_validate(arguments)


@pytest.mark.parametrize(
    "forged_fields",
    [{"customer_id": 999}, {"unit_price": "0.01"}, {"stock": 999}, {"status": "ACCEPTED"}],
)
def test_strict_catalog_tool_schema_rejects_identity_price_stock_and_status(forged_fields):
    with pytest.raises(ValidationError):
        CatalogLookupInput.model_validate({"requested_name": "SSD", **forged_fields})
