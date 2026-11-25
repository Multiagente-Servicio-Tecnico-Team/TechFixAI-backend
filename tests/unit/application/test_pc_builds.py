from decimal import Decimal

import pytest

from app.application.pc_builds import available_pc_builds, replace_pc_build_component


class Repository:
    def __init__(self, items):
        self.items = {item["code"]: item for item in items}
        self.lookups = []

    def find_spare_part_by_code(self, code):
        self.lookups.append(code)
        return self.items.get(code)


def test_pc_build_options_require_every_profile_part_in_live_stock():
    repository = Repository([
        {"id": 1, "code": "CPU-1", "name": "CPU", "category": "CPU",
         "unit_price": Decimal("120"), "current_stock": 3},
        {"id": 2, "code": "RAM-1", "name": "RAM", "category": "RAM",
         "unit_price": Decimal("40"), "current_stock": 1},
    ])
    profiles = ({
        "identifier": "office", "title": "Oficina", "uses": ("oficina",),
        "components": (("CPU", "CPU-1"), ("RAM", "RAM-1")),
        "compatibility_notes": "Verificar montaje final.",
    },)
    options = available_pc_builds(
        repository, intended_use="oficina", labor_cost=Decimal("30"), profiles=profiles
    )
    assert options[0]["total"] == Decimal("190.00")
    assert options[0]["within_budget"] is True
    assert set(repository.lookups) == {"CPU-1", "RAM-1"}


def test_pc_build_profile_is_not_offered_when_part_is_missing_or_out_of_stock():
    repository = Repository([{
        "id": 1, "code": "CPU-1", "name": "CPU", "category": "CPU",
        "unit_price": Decimal("120"), "current_stock": 0,
    }])
    profiles = ({
        "identifier": "office", "title": "Oficina", "uses": ("oficina",),
        "components": (("CPU", "CPU-1"), ("RAM", "RAM-1")),
        "compatibility_notes": "Verificar montaje final.",
    },)
    assert available_pc_builds(
        repository, intended_use="oficina", labor_cost=Decimal("30"), profiles=profiles
    ) == []


def test_pc_build_modification_revalidates_category_stock_and_price():
    repository = Repository([{
        "id": 2, "code": "RAM-2", "name": "RAM 16GB", "category": "RAM",
        "unit_price": Decimal("65"), "current_stock": 2,
    }, {
        "id": 1, "code": "RAM-1", "name": "RAM 8GB", "category": "RAM",
        "unit_price": Decimal("40"), "current_stock": 1,
    }])
    current = [{"id": 1, "code": "RAM-1", "name": "RAM 8GB", "category": "RAM",
                "quantity": 1, "unit_price": Decimal("40")}]
    revised = replace_pc_build_component(
        repository, current_parts=current, category="RAM", replacement_code="RAM-2"
    )
    assert revised[0]["code"] == "RAM-2"
    assert revised[0]["unit_price"] == Decimal("65")


def test_pc_build_modification_rejects_category_mismatch_without_selection():
    repository = Repository([{
        "id": 2, "code": "SSD-2", "name": "SSD", "category": "Storage",
        "unit_price": Decimal("60"), "current_stock": 2,
    }, {
        "id": 1, "code": "RAM-1", "name": "RAM", "category": "RAM",
        "unit_price": Decimal("40"), "current_stock": 2,
    }])
    with pytest.raises(ValueError, match="categoría"):
        replace_pc_build_component(
            repository,
            current_parts=[{"code": "RAM-1", "category": "RAM", "quantity": 1}],
            category="RAM", replacement_code="SSD-2",
        )
