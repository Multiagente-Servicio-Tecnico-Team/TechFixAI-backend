from datetime import UTC, datetime, timedelta

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.accounts.session import SessionCustomer
from app.adapters.api.sales_quotes import create_sales_quote_router


class FakeSalesRepository:
    def __init__(self):
        self.created = None
        self.accepted = None
        self.confirmed = None

    def create_direct_sales_quote(self, **values):
        self.created = values
        return {"id": 10, "customer_id": values["customer_id"], "ticket_id": None,
                "kind": "DIRECT_SALE", "status": "PENDING", "total_amount": "90.00"}

    def get_sales_quote(self, quote_id, *, customer_id=None):
        if quote_id != 10 or customer_id not in (None, 99):
            return None
        return {"id": 10, "customer_id": 99, "kind": "DIRECT_SALE", "ticket_id": None}

    def list_sales_quotes(self, **values):
        self.list_scope = values
        return [self.get_sales_quote(10, customer_id=values.get("customer_id"))]

    def accept_direct_sales_quote(self, **values):
        self.accepted = values
        return {"quote_id": values["quote_id"], "status": "ACCEPTED", "reservation_status": "RESERVED"}

    def confirm_direct_sales_payment(self, **values):
        self.confirmed = values
        return {"id": 12, "quote_id": values["quote_id"], "status": "PAID"}


def test_admin_can_create_direct_quote_and_customer_id_is_required():
    repo = FakeSalesRepository()
    app = FastAPI()
    app.include_router(create_sales_quote_router(
        require_admin=lambda: SessionCustomer(7, "Admin", None, "admin@test", "ADMIN"),
        require_customer=lambda: SessionCustomer(9, "Client", None, "client@test", "CUSTOMER", commercial_customer_id=99),
        repository_factory=lambda: repo,
    ))
    client = TestClient(app)
    response = client.post("/api/admin/sales-quotes", json={
        "customer_id": 99, "lines": [{"spare_part_id": 3, "quantity": 2}],
        "expires_at": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
    })
    assert response.status_code == 201
    assert response.json()["ticket_id"] is None
    assert repo.created["actor_user_id"] == 7
    assert client.post("/api/admin/sales-quotes", json={
        "lines": [{"spare_part_id": 3, "quantity": 2}],
        "expires_at": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
    }).status_code == 422


def test_customer_quote_list_and_acceptance_are_bound_to_resolved_session_profile():
    repo = FakeSalesRepository()
    app = FastAPI()
    app.include_router(create_sales_quote_router(
        require_admin=lambda: SessionCustomer(7, "Admin", None, "admin@test", "ADMIN"),
        require_customer=lambda: SessionCustomer(9, "Client", None, "client@test", "CUSTOMER", commercial_customer_id=99),
        repository_factory=lambda: repo,
    ))
    client = TestClient(app)
    listed = client.get("/api/customer/sales-quotes")
    assert listed.status_code == 200
    assert repo.list_scope["customer_id"] == 99
    accepted = client.post("/api/customer/sales-quotes/10/acceptance", headers={"Idempotency-Key": "accept-10"})
    assert accepted.status_code == 200
    assert repo.accepted["customer_id"] == 99
    assert repo.accepted["actor_user_id"] == 9


def test_payment_confirmation_requires_admin_and_uses_authenticated_actor():
    repo = FakeSalesRepository()
    app = FastAPI()
    app.include_router(create_sales_quote_router(
        require_admin=lambda: SessionCustomer(7, "Admin", None, "admin@test", "ADMIN"),
        require_customer=lambda: SessionCustomer(9, "Client", None, "client@test", "CUSTOMER", commercial_customer_id=99),
        repository_factory=lambda: repo,
    ))
    response = TestClient(app).post("/api/admin/sales-quotes/10/payment-confirmation",
        headers={"Idempotency-Key": "payment-10"}, json={"method": "CASH"})
    assert response.status_code == 201
    assert repo.confirmed["actor_user_id"] == 7
    assert repo.confirmed["idempotency_key"] == "payment-10"
