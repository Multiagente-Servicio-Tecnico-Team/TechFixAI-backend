from pathlib import Path

import yaml


CONTRACT = Path(__file__).parents[2] / "specs/003-asientos-contables/contracts/accounting.openapi.yaml"


def test_contract_contains_accounting_routes_and_idempotency_header():
    contract = yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))
    paths = contract["paths"]
    assert {"get", "post"} <= set(paths["/api/admin/accounting/entries"])
    assert "post" in paths["/api/admin/accounting/entries/{entry_id}/reverse"]
    header = paths["/api/admin/accounting/entries"]["post"]["parameters"][0]
    assert header["name"] == "Idempotency-Key" and header["required"] is True


def test_contract_documents_admin_only_and_pagination_constraints():
    contract = yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))
    assert "ADMIN role" in contract["info"]["description"]
    limit = next(p for p in contract["paths"]["/api/admin/accounting/entries"]["get"]["parameters"] if p["name"] == "limit")
    assert limit["schema"]["maximum"] == 100


def test_contract_list_filters_and_detail_are_sufficient_for_frontend():
    contract = yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))
    listing = contract["paths"]["/api/admin/accounting/entries"]["get"]
    parameters = {parameter["name"] for parameter in listing["parameters"]}
    assert {"from_date", "to_date", "category_id", "status", "entry_number", "limit", "offset"} <= parameters
    summary_schema = contract["components"]["schemas"]["AccountingEntrySummary"]
    assert "updated_at" in summary_schema["required"]
    assert summary_schema["properties"]["amount"]["type"] == "string"
    detail = contract["paths"]["/api/admin/accounting/entries/{entry_id}"]["get"]
    assert "404" in detail["responses"]


def test_contract_describes_reversal_replay_and_conflicts():
    contract = yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))
    reverse = contract["paths"]["/api/admin/accounting/entries/{entry_id}/reverse"]["post"]
    assert {"201", "200", "409", "422"} <= set(reverse["responses"])
    assert reverse["responses"]["201"]["content"]["application/json"]["schema"]["$ref"].endswith("/ReversalResult")
