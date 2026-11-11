from decimal import Decimal

import pytest

from app.agents.jerarquico.warehouse import make_warehouse_agent
from app.application.catalog import CatalogService


class CatalogRepository:
    """Repository double: the values here represent the database boundary."""

    def __init__(self, *, items=None, match_status="exact"):
        self.items = items or [{
            "id": 21,
            "code": "SSD-NVME-512",
            "name": "SSD NVMe 512GB",
            "category": "Almacenamiento",
            "unit_price": Decimal("44.90"),
            "current_stock": 5,
        }]
        self.match_status = match_status

    def lookup_inventory(self, name, quantity):
        if self.match_status != "exact":
            return {
                "requested_name": name,
                "name": name,
                "quantity": quantity,
                "stock": 0,
                "unit_price": Decimal("0.00"),
                "available": False,
                "found": False,
                "match_status": self.match_status,
            }
        item = self.items[0]
        stock = item["current_stock"]
        return {
            "requested_name": name,
            "name": item["name"],
            "quantity": quantity,
            "stock": stock,
            "unit_price": item["unit_price"],
            "available": stock >= quantity,
            "found": True,
            "match_status": "exact",
        }

    def find_spare_parts(self, search_term):
        return self.items

    def find_catalog_items(self, search_term, *, limit=20):
        return self.items[:limit]

    def find_spare_part_by_code(self, code):
        return next((item for item in self.items if item["code"] == code), None)

    def find_spare_part_alternatives(self, search_term):
        return self.items


def run_pattern_catalog(pattern_id, repository, monkeypatch, quantity=2):
    # Los tres patrones usan el mismo agente de almacén compartido (make_worker_nodes).
    agent = make_warehouse_agent(repository)
    return agent({
        "request_type": "SALE",
        "required_parts": [{"search_term": "SSD NVMe 512GB", "quantity": quantity}],
        "messages": [],
    })


@pytest.mark.parametrize("pattern_id", ["hierarchical", "orchestrator", "decentralized"])
def test_exact_catalog_match_uses_repository_price_and_live_stock(pattern_id, monkeypatch):
    repository = CatalogRepository()
    result = run_pattern_catalog(pattern_id, repository, monkeypatch)

    item = result["matched_parts"][0]
    assert item["unit_price"] == Decimal("44.90")
    assert item["current_stock"] == 5


@pytest.mark.parametrize("pattern_id", ["hierarchical", "orchestrator", "decentralized"])
def test_ambiguous_catalog_does_not_choose_or_report_available_item(pattern_id, monkeypatch):
    candidates = [
        {"id": 21, "code": "SSD-A", "name": "SSD NVMe A", "category": "Almacenamiento",
         "unit_price": Decimal("44.90"), "current_stock": 5},
        {"id": 22, "code": "SSD-B", "name": "SSD NVMe B", "category": "Almacenamiento",
         "unit_price": Decimal("49.90"), "current_stock": 3},
    ]
    repository = CatalogRepository(items=candidates, match_status="ambiguous")
    result = run_pattern_catalog(pattern_id, repository, monkeypatch)

    assert result["outcome"] == "awaiting_inventory_selection"
    assert len(result["inventory_options"]) == 2
    assert result["matched_parts"] == []


@pytest.mark.parametrize("pattern_id", ["hierarchical", "orchestrator", "decentralized"])
def test_insufficient_stock_is_not_reported_as_available(pattern_id, monkeypatch):
    item = {"id": 21, "code": "SSD-NVME-512", "name": "SSD NVMe 512GB",
            "category": "Almacenamiento", "unit_price": Decimal("44.90"),
            "current_stock": 1}
    repository = CatalogRepository(items=[item])
    result = run_pattern_catalog(pattern_id, repository, monkeypatch, quantity=2)

    assert result["outcome"] == "inventory_unavailable"
    assert result.get("matched_parts", []) == []
