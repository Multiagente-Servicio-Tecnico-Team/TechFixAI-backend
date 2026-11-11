from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.accounts.session import SessionCustomer
from app.adapters.api.admin_tickets import create_admin_ticket_router
from app.adapters.api.chat import create_chat_router
from app.application.tickets import ListCustomerTickets
from app.adapters.api.chat import ticket_json
from app.domain.tickets import CustomerTicket, TicketQuote


class TicketRepository:
    def __init__(self):
        self.values = None
        self.actor_id = None

    def create_admin_ticket(self, *, values, code, actor_id):
        self.values, self.actor_id = values, actor_id
        return 1

    def get_admin_ticket(self, _ticket_id):
        return {"id": 1, "code": "TCK-1", "customer_id": 99, "contact_name": "Ana Rojas",
                "contact_phone": "987654321", "contact_email": None, "origin": "MANUAL",
                "title": "Laptop", "failure_description": "No enciende", "request_type": "REPAIR",
                "status": "NEW", "estimated_labor_hours": 0, "advance_amount": None,
                "payment_amount": None, "payment_method": None, "quote_id": None}

    def list_ticket_audit_events(self, _ticket_id):
        return [{"actor_user_id": 7, "event_type": "CREATED", "created_at": "2026-11-03T00:00:00Z"}]


class TicketUseCase:
    def __init__(self):
        self.customer_id = None

    def execute(self, customer_id):
        self.customer_id = customer_id
        return []


def test_admin_ticket_can_reference_commercial_customer_and_actor_is_separate():
    repo = TicketRepository()
    app = FastAPI()
    app.include_router(create_admin_ticket_router(
        require_admin=lambda: SessionCustomer(7, "Admin", None, "admin@example.test", "ADMIN"),
        repository_factory=lambda: repo,
    ))
    response = TestClient(app).post("/api/admin/tickets", json={
        "customer_id": 99, "contact_name": "Ana Rojas", "contact_phone": "987654321",
        "title": "Laptop", "failure_description": "No enciende el equipo", "request_type": "REPAIR"
    })
    assert response.status_code == 201
    assert repo.values["customer_id"] == 99
    assert repo.actor_id == 7
    assert response.json()["customer_id"] == 99


def test_customer_ticket_listing_uses_commercial_profile_resolved_by_session():
    list_tickets = TicketUseCase()
    app = FastAPI()
    app.include_router(create_chat_router(
        send_message=None,
        list_tickets=list_tickets,
        require_customer=lambda: SessionCustomer(7, "Ana", "Rojas", "ana@example.test", "CUSTOMER", "987654321", 99),
        pattern_names={},
    ))
    response = TestClient(app).get("/api/customer/tickets")
    assert response.status_code == 200
    assert list_tickets.customer_id == 99


def test_portal_ticket_creation_uses_session_profile_and_service_types_only():
    recorded = {}
    app = FastAPI()
    app.include_router(create_chat_router(
        send_message=None,
        list_tickets=TicketUseCase(),
        require_customer=lambda: SessionCustomer(7, "Ana", "Rojas", "ana@example.test", "CUSTOMER", "987654321", 99),
        pattern_names={},
        create_portal_ticket=lambda **values: recorded.update(values) or {"id": 2, "status": "NEW"},
    ))
    response = TestClient(app).post("/api/customer/tickets", json={
        "customer_id": 500, "title": "Laptop", "failure_description": "No enciende el equipo", "request_type": "REPAIR"
    })
    assert response.status_code == 422
    response = TestClient(app).post("/api/customer/tickets", json={
        "title": "Laptop", "failure_description": "No enciende el equipo", "request_type": "REPAIR"
    })
    assert response.status_code == 201
    assert recorded["customer_id"] == 99


def test_portal_ticket_response_exposes_customer_and_multiple_service_quotes():
    ticket = CustomerTicket(
        id=5, customer_id=99, code="TCK-5", title="Laptop",
        failure_description="No enciende", request_type="REPAIR", status="QUOTED",
        quotes=(
            TicketQuote("PENDING", 10, 0, 10, "2026-11-01T00:00:00Z"),
            TicketQuote("ACCEPTED", 20, 5, 25, "2026-11-02T00:00:00Z"),
        ),
    )
    result = ticket_json(ticket)
    assert result["customer_id"] == 99
    assert result["id"] == 5
    assert [quote["total_amount"] for quote in result["quotes"]] == ["10.00", "25.00"]
