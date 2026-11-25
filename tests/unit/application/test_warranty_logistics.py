from datetime import date, timedelta

import pytest

from app.application.logistics import record_customer_logistics_preference
from app.application.warranties import (
    lookup_customer_warranty,
    register_customer_warranty_claim,
)


class Repository:
    def __init__(self, warranty=None):
        self.warranty = warranty
        self.claims = []
        self.logistics = []

    def find_warranty(self, code):
        assert code == "WAR-41"
        return self.warranty

    def create_warranty_claim(self, **values):
        self.claims.append(values)

    def create_logistics_record(self, **values):
        self.logistics.append(values)
        return 99


@pytest.fixture
def active_warranty():
    return {
        "id": 8, "customer_id": 41, "warranty_code": "WAR-41",
        "status": "ACTIVE", "not_expired": True,
        "end_date": date.today() + timedelta(days=20),
        "item_or_service_name": "PC",
    }


def test_warranty_lookup_hides_other_customers(active_warranty):
    repository = Repository(active_warranty)
    assert lookup_customer_warranty(
        repository, customer_id=42, warranty_code="WAR-41"
    ) is None


def test_warranty_claim_requires_owned_active_policy_and_records_once(active_warranty):
    repository = Repository(active_warranty)
    result = register_customer_warranty_claim(
        repository, customer_id=41, ticket_id=31, warranty_code="WAR-41",
        reason="El equipo dejó de encender", claim_code="CLM-41",
    )
    assert result["claim_code"] == "CLM-41"
    assert repository.claims == [{
        "warranty_id": 8, "ticket_id": 31, "customer_id": 41,
        "claim_code": "CLM-41", "reason": "El equipo dejó de encender",
    }]


@pytest.mark.parametrize("mutation", [
    {"customer_id": 42}, {"status": "EXPIRED"}, {"not_expired": False},
])
def test_ineligible_warranty_claim_performs_zero_writes(active_warranty, mutation):
    repository = Repository({**active_warranty, **mutation})
    with pytest.raises((LookupError, PermissionError, ValueError)):
        register_customer_warranty_claim(
            repository, customer_id=41, ticket_id=31, warranty_code="WAR-41",
            reason="No funciona", claim_code="CLM-41",
        )
    assert repository.claims == []


def test_logistics_requires_customer_owned_ticket_context_and_courier_details():
    repository = Repository()
    with pytest.raises(ValueError):
        record_customer_logistics_preference(
            repository, customer_id=41, ticket_id=31, mode="COURIER_SHIPMENT"
        )
    assert repository.logistics == []

    record_id = record_customer_logistics_preference(
        repository, customer_id=41, ticket_id=31, mode="COURIER_SHIPMENT",
        courier_company="Courier Uno", shipping_address="Calle 1 # 2-3",
    )
    assert record_id == 99
    assert repository.logistics[0]["customer_id"] == 41


@pytest.mark.parametrize("customer_id,ticket_id,mode", [
    (0, 31, "PHYSICAL_STORE"), (41, 0, "PHYSICAL_STORE"),
    (41, 31, "UNKNOWN"),
])
def test_invalid_logistics_input_performs_zero_writes(customer_id, ticket_id, mode):
    repository = Repository()
    with pytest.raises((ValueError, PermissionError)):
        record_customer_logistics_preference(
            repository, customer_id=customer_id, ticket_id=ticket_id, mode=mode
        )
    assert repository.logistics == []
