from datetime import date, timedelta

import pytest

import app.agents.decentralized.tools.soporte_tools as tools


class Repository:
    def __init__(self, owner=41, active=True):
        self.owner = owner
        self.active = active
        self.claims = []
        self.logistics = []

    def find_warranty(self, code):
        return {"id": 4, "customer_id": self.owner, "warranty_code": code,
                "status": "ACTIVE" if self.active else "EXPIRED",
                "not_expired": self.active, "end_date": date.today() + timedelta(days=2),
                "item_or_service_name": "Laptop"}

    def create_warranty_claim(self, **values): self.claims.append(values)
    def create_logistics_record(self, **values): self.logistics.append(values); return 9


def test_decentralized_warranty_tool_hides_unowned_policy(monkeypatch):
    monkeypatch.setattr(tools, "ticket_repository", Repository(owner=42))
    result = tools.consultar_estado_garantia.invoke({
        "warranty_code": "WAR-4", "state": {"customer_id": 41},
    })
    assert "No encontré" in result


def test_decentralized_claim_tool_writes_only_owned_active_policy(monkeypatch):
    repository = Repository()
    monkeypatch.setattr(tools, "ticket_repository", repository)
    result = tools.registrar_reclamo_garantia.invoke({
        "warranty_code": "WAR-4", "reason": "No enciende",
        "state": {"customer_id": 41, "ticket_id": 15},
    })
    assert "revisión manual" in result
    assert repository.claims[0]["ticket_id"] == 15


@pytest.mark.parametrize("state", [{"customer_id": 41}, {"customer_id": 41, "ticket_id": 15}])
def test_decentralized_logistics_tool_requires_courier_data_or_ticket(monkeypatch, state):
    repository = Repository()
    monkeypatch.setattr(tools, "ticket_repository", repository)
    payload = {"mode": "COURIER_SHIPMENT", "state": state}
    if "ticket_id" in state:
        with pytest.raises(ValueError, match="Courier"):
            tools.registrar_preferencia_logistica.invoke(payload)
    else:
        assert "Necesito un ticket" in tools.registrar_preferencia_logistica.invoke(payload)
    assert repository.logistics == []


def test_decentralized_logistics_records_only_pending_preference(monkeypatch):
    repository = Repository()
    monkeypatch.setattr(tools, "ticket_repository", repository)
    result = tools.registrar_preferencia_logistica.invoke({
        "mode": "COURIER_SHIPMENT", "courier_company": "Courier Uno",
        "shipping_address": "Calle 1", "state": {"customer_id": 41, "ticket_id": 15},
    })
    assert "pendiente de recepción" in result
    assert repository.logistics[0]["customer_id"] == 41
