from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.adapters.tools.catalog import CatalogLookupInput, make_catalog_lookup_tool
from app.adapters.tools.quotes import (
    QuoteCalculationInput,
    make_quote_calculation_tool,
)
from app.application.catalog import CatalogService
from app.application.ports import CustomerContext


class CatalogRepository:
    def lookup_inventory(self, name, quantity):
        return {
            "requested_name": name,
            "name": "SSD NVMe 512GB",
            "quantity": quantity,
            "stock": 4,
            "unit_price": Decimal("44.90"),
            "available": quantity <= 4,
            "found": True,
            "match_status": "exact",
        }

    def find_spare_parts(self, term):
        return []

    def find_catalog_items(self, term, *, limit=20):
        return []

    def find_spare_part_by_code(self, code):
        if code != "SSD-NVME-512":
            return None
        return {
            "id": 7,
            "code": code,
            "name": "SSD NVMe 512GB",
            "category": "Almacenamiento",
            "unit_price": Decimal("44.90"),
            "current_stock": 4,
        }

    def find_spare_part_alternatives(self, term):
        return []


@pytest.fixture
def tool_context():
    return CustomerContext(17, "conversation-test", "hierarchical")


def test_tool_schemas_reject_identity_and_financial_overrides():
    with pytest.raises(ValidationError):
        CatalogLookupInput.model_validate({
            "requested_name": "SSD", "customer_id": 999, "unit_price": "0.01",
        })
    with pytest.raises(ValidationError):
        QuoteCalculationInput.model_validate({
            "parts": [{"code": "SSD-NVME-512", "quantity": 1,
                       "unit_price": "0.01", "stock": 999}],
            "customer_id": 999,
            "total_amount": "0.01",
        })
    with pytest.raises(ValidationError):
        QuoteCalculationInput.model_validate({
            "parts": [{"code": "SSD-NVME-512", "quantity": True}],
        })


def test_catalog_tool_returns_only_server_inventory_values(tool_context):
    tool = make_catalog_lookup_tool(
        CatalogService(CatalogRepository()), customer_context=tool_context,
    )

    result = tool.invoke({"requested_name": "SSD NVMe 512GB", "quantity": 2})

    assert result["unit_price"] == "44.90"
    assert result["stock"] == 4
    assert result["available"] is True


def test_quote_tool_uses_server_prices_labor_and_authenticated_context(tool_context):
    tool = make_quote_calculation_tool(
        CatalogService(CatalogRepository()),
        customer_context=tool_context,
        labor_task_type="maintenance",
        labor_cost=Decimal("35.00"),
        quote_type="REPAIR",
    )

    quote = tool.invoke({"parts": [{"code": "SSD-NVME-512", "quantity": 2}]})

    assert quote["quote_type"] == "REPAIR"
    assert quote["labor_cost"] == Decimal("35.00")
    assert quote["parts_cost"] == Decimal("89.80")
    assert quote["total_amount"] == Decimal("124.80")
    assert quote["parts"][0]["unit_price"] == Decimal("44.90")


def test_quote_tool_refuses_unknown_or_insufficient_catalog_items(tool_context):
    tool = make_quote_calculation_tool(
        CatalogService(CatalogRepository()),
        customer_context=tool_context,
        labor_task_type="maintenance",
        labor_cost=Decimal("35.00"),
        quote_type="REPAIR",
    )
    with pytest.raises(LookupError):
        tool.invoke({"parts": [{"code": "UNKNOWN", "quantity": 1}]})
    with pytest.raises(ValueError, match="stock"):
        tool.invoke({"parts": [{"code": "SSD-NVME-512", "quantity": 5}]})
