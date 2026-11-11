from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.accounts.session import SessionCustomer
from app.adapters.api.customers import create_customer_router


class FakeCustomers:
    def __init__(self):
        self.rows = []

    def create_customer(self, *, draft, actor_id):
        row = {"id": 1, "display_name": draft.display_name, "phone": draft.phone,
               "email": draft.email, "origin": draft.origin.value, "user_id": None,
               "created_by_user_id": actor_id, "account_linked": False}
        self.rows.append(row)
        return row

    def list_customers(self, **_filters):
        return {"items": list(self.rows), "total": len(self.rows)}

    def get_customer(self, customer_id):
        return next((row for row in self.rows if row["id"] == customer_id), None)


def make_client(repository, *, allowed=True):
    app = FastAPI()

    def require_admin():
        if not allowed:
            raise HTTPException(status_code=403, detail="admin_only")
        return SessionCustomer(9, "Admin", None, "admin@example.com", "ADMIN")

    app.include_router(create_customer_router(require_admin=require_admin, repository_factory=lambda: repository))
    return TestClient(app)


def test_admin_can_create_manual_customer_without_creating_user():
    repository = FakeCustomers()
    response = make_client(repository).post("/api/admin/customers", json={
        "display_name": "Cliente Presencial", "phone": "987654321", "email": None
    })
    assert response.status_code == 201
    assert response.json()["origin"] == "MANUAL"
    assert response.json()["user_id"] is None
    assert response.json()["created_by_user_id"] == 9


def test_customer_admin_routes_require_admin_role():
    response = make_client(FakeCustomers(), allowed=False).get("/api/admin/customers")
    assert response.status_code == 403


def test_customer_create_rejects_extra_identity_fields():
    response = make_client(FakeCustomers()).post("/api/admin/customers", json={
        "display_name": "Cliente", "phone": "987654321", "user_id": 99
    })
    assert response.status_code == 422
