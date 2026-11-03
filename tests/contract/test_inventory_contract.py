from pathlib import Path

import yaml


CONTRACT = Path(__file__).parents[2] / "specs/005-api-inventario/contracts/inventory.openapi.yaml"


def test_inventory_contract_exposes_frontend_routes_and_methods():
    document = yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))
    paths = document["paths"]
    assert {"get", "post"} <= set(paths["/api/inventory/parts"])
    assert {"put", "delete"} <= set(paths["/api/inventory/parts/{code}"])
    assert "get" in paths["/api/inventory/categories"]


def test_inventory_contract_preserves_money_string_and_resource_fields():
    document = yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))
    part = document["components"]["schemas"]["InventoryPart"]
    assert {"code", "name", "category", "description", "unit_price", "current_stock",
            "minimum_threshold", "active", "created_at", "updated_at"} <= set(part["required"])
    assert part["properties"]["unit_price"]["type"] == "string"


def test_inventory_contract_documents_staff_session_and_errors():
    document = yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))
    assert document["components"]["securitySchemes"]["sessionCookie"]["name"] == "techfix_session"
    for path, method in (
        ("/api/inventory/parts", "get"),
        ("/api/inventory/parts", "post"),
        ("/api/inventory/parts/{code}", "put"),
        ("/api/inventory/parts/{code}", "delete"),
        ("/api/inventory/categories", "get"),
    ):
        operation = document["paths"][path][method]
        assert operation["security"] == [{"sessionCookie": []}]
        assert "401" in operation["responses"] and "403" in operation["responses"]
