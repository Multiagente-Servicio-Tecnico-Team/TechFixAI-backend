"""Chat ADMIN: la consulta de inventario puede filtrar los repuestos con stock bajo."""
from decimal import Decimal

import pytest

from app.domain.inventory import InventoryPart, is_low_stock
from app.infrastructure.admin_capabilities import AdminCapabilityService
from app.infrastructure.admin_chat import capability_argument_hints


def _part(part_id, code, stock, minimum, category="Memoria"):
    return InventoryPart(id=part_id, code=code, name=f"Repuesto {code}", category=category, description=None,
                         unit_price=Decimal("10.00"), current_stock=stock, minimum_threshold=minimum,
                         active=True, created_at="2026-11-25T10:00:00", updated_at="2026-11-25T10:00:00")


class _Inventory:
    def list_parts(self):
        return [_part(1, "RAM-8", 20, 5), _part(2, "SSD-1T", 3, 3, "Almacenamiento"),
                _part(3, "CPU-R5", 1, 4, "Procesador"), _part(4, "FAN-12", 9, 2, "Ventilación")]


def _service():
    return AdminCapabilityService(inventory_repository_factory=_Inventory)


@pytest.mark.parametrize(("stock", "minimum", "expected"), [(0, 0, True), (2, 3, True), (3, 3, True), (4, 3, False)])
def test_low_stock_rule_includes_the_minimum(stock, minimum, expected):
    assert is_low_stock(stock, minimum) is expected


def test_inventory_list_returns_only_low_stock_parts_when_requested():
    result = _service().read("inventory.list", {"low_stock": True})
    assert [item["code"] for item in result["items"]] == ["SSD-1T", "CPU-R5"]
    assert result["total"] == 2


def test_inventory_list_without_filter_keeps_every_part():
    result = _service().read("inventory.list", {})
    assert result["total"] == 4


def test_low_stock_combines_with_search():
    result = _service().read("inventory.list", {"low_stock": True, "search": "procesador"})
    assert [item["code"] for item in result["items"]] == ["CPU-R5"]


def test_low_stock_is_rejected_for_other_resources():
    with pytest.raises(ValueError):
        AdminCapabilityService().read("suppliers.list", {"low_stock": True})


def test_argument_hints_explain_the_low_stock_filter():
    assert "low_stock:boolean" in capability_argument_hints()
