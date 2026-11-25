from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.accounts.session import SessionCustomer
from app.adapters.api.purchase_orders import create_purchase_order_router
from app.application.errors import PurchaseOrderConflict, PurchaseOrderNotFound


ORDER = {
    "id": 31,
    "supplier_id": 7,
    "supplier_name": "Distribuidora Tech",
    "status": "DRAFT",
    "total_amount": "96.00",
    "currency": "PEN",
    "estimated_arrival": None,
    "created_by": 8,
    "created_at": "2026-11-09T10:00:00+00:00",
    "updated_at": "2026-11-09T10:00:00+00:00",
    "notes": None,
    "items": [{
        "id": 1,
        "spare_part_id": 4,
        "code_snapshot": "RAM-4",
        "description_snapshot": "Memoria DDR4",
        "quantity_ordered": "2",
        "quantity_received": "0",
        "quantity_pending": "2",
        "quantity_invoiced": "0",
        "quantity_cancelled": "0",
        "unit_cost": "45.50",
        "subtotal": "91.00",
    }],
    "receipts": [],
    "linked_purchases": [],
    "audit_events": [],
}


class FakeRepository:
    def __init__(self, *, error=None):
        self.error = error
        self.stock = 12
        self.calls = []
        self.status = "DRAFT"

    def create_order(self, *, actor_id, draft):
        self.calls.append(("create", actor_id, draft))
        if self.error:
            raise self.error
        return dict(ORDER)

    def get_order(self, order_id):
        self.calls.append(("get", order_id))
        return dict(ORDER) if order_id == ORDER["id"] else None

    def update_order(self, *, actor_id, order_id, draft, changed_fields):
        self.calls.append(("update", actor_id, order_id, changed_fields))
        if self.error:
            raise self.error
        if self.status != "DRAFT":
            raise PurchaseOrderConflict("Solo se pueden editar órdenes en borrador.")
        return dict(ORDER)

    def issue_order(self, *, actor_id, order_id):
        self.calls.append(("issue", actor_id, order_id))
        if self.error:
            raise self.error
        if self.status != "DRAFT":
            raise PurchaseOrderConflict("Solo se puede emitir una orden en borrador.")
        self.status = "ISSUED"
        order = dict(ORDER)
        order["status"] = "ISSUED"
        order["issued_by"] = actor_id
        order["issued_at"] = "2026-11-09T11:00:00+00:00"
        return order

    def cancel_order(self, *, actor_id, order_id, reason):
        self.calls.append(("cancel", actor_id, order_id, reason))
        if self.error:
            raise self.error
        if self.status in {"RECEIVED", "CANCELLED"}:
            raise PurchaseOrderConflict("No se puede cancelar una orden recibida o ya cancelada.")
        self.status = "CANCELLED"
        order = dict(ORDER)
        order["status"] = "CANCELLED"
        order["cancelled_by"] = actor_id
        order["cancellation_reason"] = reason
        return order

    def list_orders(self, **filters):
        self.calls.append(("list", filters))
        return {"items": [], "total": 0, "limit": filters["limit"], "offset": filters["offset"]}


def client_for(repository, *, admin=True):
    def require_admin():
        if not admin:
            raise HTTPException(status_code=403, detail="Solo administradores.")
        return SessionCustomer(8, "Ana", "Admin", "admin@example.test", "ADMIN")

    app = FastAPI()
    app.include_router(create_purchase_order_router(
        require_admin=require_admin,
        repository_factory=lambda: repository,
    ))
    return TestClient(app)


def sample_payload():
    return {
        "supplier_id": 7,
        "items": [
            {"spare_part_id": 4, "description": "Memoria DDR4", "quantity": 2, "unit_cost": "45.50"},
            {"description": "Servicio de embalaje", "quantity": 1, "unit_cost": "5.00"},
        ],
    }


def test_create_and_read_draft_without_stock_change():
    repository = FakeRepository()
    client = client_for(repository)
    created = client.post("/api/admin/purchase-orders", json=sample_payload())
    detail = client.get("/api/admin/purchase-orders/31")
    assert created.status_code == 201
    assert created.json()["order"]["status"] == "DRAFT"
    assert detail.status_code == 200
    assert detail.json()["order"]["total_amount"] == "96.00"
    assert repository.stock == 12
    assert [call[0] for call in repository.calls] == ["create", "get"]
    assert repository.calls[0][1] == 8


def test_order_routes_require_admin():
    response = client_for(FakeRepository(), admin=False).post(
        "/api/admin/purchase-orders", json=sample_payload()
    )
    assert response.status_code == 403


def test_admin_can_issue_and_cancel_orders_with_audit_actor():
    repository = FakeRepository()
    client = client_for(repository)
    issued = client.post("/api/admin/purchase-orders/31/issue")
    cancelled = client.post("/api/admin/purchase-orders/31/cancel", json={"reason": "Pedido descontinuado"})
    assert issued.status_code == 200
    assert issued.json()["order"]["issued_by"] == 8
    assert cancelled.status_code == 200
    assert cancelled.json()["order"]["cancelled_by"] == 8
    assert cancelled.json()["order"]["cancellation_reason"] == "Pedido descontinuado"


def test_issued_order_cannot_be_issued_twice_or_edited():
    repository = FakeRepository()
    client = client_for(repository)
    issued = client.post("/api/admin/purchase-orders/31/issue")
    duplicate_issue = client.post("/api/admin/purchase-orders/31/issue")
    edit_issued = client.patch("/api/admin/purchase-orders/31", json={"notes": "change"})
    assert issued.status_code == 200
    assert duplicate_issue.status_code == 409
    assert edit_issued.status_code == 409


def test_cancel_requires_reason_and_repository_state_conflicts_return_409():
    repository = FakeRepository()
    client = client_for(repository)
    missing_reason = client.post("/api/admin/purchase-orders/31/cancel", json={})
    conflict = client_for(FakeRepository(error=PurchaseOrderConflict("La orden ya fue recibida."))).post(
        "/api/admin/purchase-orders/31/cancel", json={"reason": "Anular"}
    )
    assert missing_reason.status_code == 422
    assert conflict.status_code == 409


def test_admin_can_edit_a_draft_order():
    repository = FakeRepository()
    response = client_for(repository).patch(
        "/api/admin/purchase-orders/31",
        json={"notes": "Confirmar disponibilidad"},
    )
    assert response.status_code == 200
    assert response.json()["order"]["status"] == "DRAFT"
    assert repository.calls[0] == ("get", 31)
    assert repository.calls[1][0:3] == ("update", 8, 31)


def test_empty_patch_is_rejected_before_repository():
    repository = FakeRepository()
    response = client_for(repository).patch("/api/admin/purchase-orders/31", json={})
    assert response.status_code == 422
    assert repository.calls == []


def test_invalid_order_line_is_rejected_before_repository():
    repository = FakeRepository()
    payload = sample_payload()
    payload["items"][0]["quantity"] = 0
    response = client_for(repository).post("/api/admin/purchase-orders", json=payload)
    assert response.status_code == 422
    assert repository.calls == []


def test_inactive_or_missing_supplier_returns_not_found():
    repository = FakeRepository(error=PurchaseOrderNotFound())
    response = client_for(repository).post("/api/admin/purchase-orders", json=sample_payload())
    assert response.status_code == 404
    assert response.json()["code"] == "purchase_order_not_found"


def test_list_orders_accepts_filters_and_returns_page_metadata():
    repository = FakeRepository()
    response = client_for(repository).get(
        "/api/admin/purchase-orders?supplier_id=7&status=ISSUED&date_from=2026-11-01&date_to=2026-11-30&limit=25&offset=50"
    )
    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0, "limit": 25, "offset": 50}
    assert repository.calls[0][0] == "list"
    assert repository.calls[0][1]["supplier_id"] == 7


def test_list_orders_rejects_invalid_status_and_inverted_dates():
    client = client_for(FakeRepository())
    invalid_status = client.get("/api/admin/purchase-orders?status=UNKNOWN")
    inverted_dates = client.get("/api/admin/purchase-orders?date_from=2026-11-30&date_to=2026-11-01")
    assert invalid_status.status_code == 422
    assert inverted_dates.status_code == 422
