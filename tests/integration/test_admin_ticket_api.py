from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.accounts.session import SessionCustomer
from app.adapters.api.admin_tickets import create_admin_ticket_router


class FakeTickets:
    def __init__(self):
        self.ticket = None
        self.actor = None
        self.events = []

    def create_admin_ticket(self, *, values, code, actor_id):
        self.ticket = {"id": 7, "code": code, **values, "created_at": datetime.now(timezone.utc), "updated_at": None}
        self.actor = actor_id
        self.events = [{"event_type": "CREATED", "actor_user_id": actor_id, "changed_fields": {"origin": "MANUAL"}, "created_at": datetime.now(timezone.utc)}]
        return 7

    def get_admin_ticket(self, ticket_id):
        if ticket_id != 7 or self.ticket is None:
            return None
        return {"customer_first_name": None, "customer_last_name": None, "customer_email": None,
                "customer_phone": None, "quote_total": None, "payment_amount": None,
                "estimated_labor_hours": 0, "payment_status": None, "payment_method": None, **self.ticket}

    def list_ticket_audit_events(self, ticket_id):
        return self.events

    def update_admin_ticket_audited(self, ticket_id, values, actor_id):
        self.ticket.update(values)
        self.events.append({"event_type": "UPDATED", "actor_user_id": actor_id, "changed_fields": values, "created_at": datetime.now(timezone.utc)})
        return True

    def list_admin_tickets(self, **filters):
        return {"items": [self.get_admin_ticket(7)], "total": 1}


def test_admin_can_create_manual_ticket_without_customer_account_and_delete_is_disabled():
    repository = FakeTickets()
    app = FastAPI()
    app.include_router(create_admin_ticket_router(
        require_admin=lambda: SessionCustomer(id=4, first_name="Admin", last_name=None, email="admin@example.test", role="ADMIN"),
        repository_factory=lambda: repository,
    ))
    client = TestClient(app)
    response = client.post("/api/admin/tickets", json={
        "contact_name": "Cliente de mostrador", "contact_phone": "999111222",
        "title": "Laptop Lenovo", "failure_description": "No enciende el equipo",
        "request_type": "REPAIR",
    })
    assert response.status_code == 201
    assert response.json()["origin"] == "MANUAL"
    assert response.json()["customer_id"] is None
    assert repository.actor == 4
    assert response.json()["audit_events"][0]["actor_user_id"] == 4
    assert client.delete("/api/admin/tickets/7").status_code == 409


def test_admin_manual_advance_requires_a_method():
    app = FastAPI()
    app.include_router(create_admin_ticket_router(
        require_admin=lambda: SessionCustomer(id=4, first_name="Admin", last_name=None, email="admin@example.test", role="ADMIN"),
        repository_factory=FakeTickets,
    ))
    response = TestClient(app).post("/api/admin/tickets", json={
        "contact_name": "Cliente de mostrador", "contact_phone": "999111222",
        "title": "Laptop Lenovo", "failure_description": "No enciende el equipo",
        "request_type": "REPAIR", "advance_amount": "50.00",
    })
    assert response.status_code == 422


def test_admin_ticket_list_returns_filtered_pagination_shape_and_patch_audit():
    repository = FakeTickets()
    repository.create_admin_ticket(values={
        "customer_id": None, "origin": "MANUAL", "contact_name": "Cliente", "contact_phone": "999111222",
        "contact_email": None, "advance_amount": None, "advance_payment_method": None,
        "title": "Laptop Lenovo", "failure_description": "No enciende el equipo", "request_type": "REPAIR",
        "diagnosis_type": "NONE", "status": "NEW", "technician_id": None,
        "estimated_labor_hours": 0, "is_remote_service": False, "hardware_diagnosis": None, "software_diagnosis": None,
    }, code="TCK-EXAMPLE", actor_id=4)
    app = FastAPI()
    app.include_router(create_admin_ticket_router(
        require_admin=lambda: SessionCustomer(id=4, first_name="Admin", last_name=None, email="admin@example.test", role="ADMIN"),
        repository_factory=lambda: repository,
    ))
    client = TestClient(app)
    listing = client.get("/api/admin/tickets?origin=MANUAL&limit=1&offset=0").json()
    assert set(listing) == {"items", "total", "limit", "offset"}
    assert listing["total"] == 1 and listing["items"][0]["origin"] == "MANUAL"
    updated = client.patch("/api/admin/tickets/7", json={"status": "CANCELLED"})
    assert updated.status_code == 200
    assert updated.json()["audit_events"][-1]["actor_user_id"] == 4
