from pathlib import Path
import yaml


CONTRACT = Path(__file__).parents[2] / "specs/004-gestion-admin-tickets/contracts/admin-tickets.openapi.yaml"


def test_admin_ticket_list_has_filters_and_stable_pagination_contract():
    spec = yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))
    listing = spec["paths"]["/api/admin/tickets"]["get"]
    names = {item["name"] for item in listing["parameters"]}
    assert {"status", "request_type", "origin", "search", "limit", "offset"} <= names
    props = listing["responses"]["200"]["content"]["application/json"]["schema"]["properties"]
    assert {"items", "total", "limit", "offset"} <= props.keys()
