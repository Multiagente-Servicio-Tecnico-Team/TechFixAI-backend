from pathlib import Path
import yaml


CONTRACT = Path(__file__).parents[2] / "specs/004-gestion-admin-tickets/contracts/admin-tickets.openapi.yaml"


def test_create_contract_requires_manual_contact_and_server_owned_origin():
    spec = yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))
    create = spec["components"]["schemas"]["CreateManualTicket"]
    assert {"contact_name", "contact_phone", "title", "failure_description", "request_type"} <= set(create["required"])
    assert "origin" not in create["properties"]
    assert "customer_email" not in create["properties"]
