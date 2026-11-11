from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import inspect

from app.accounts.session import SessionCustomer
from app.adapters.api.purchase_orders import create_purchase_order_router
from app.application.errors import PurchaseOrderConflict


class ReceiptRepository:
    def __init__(self, *, status="ISSUED", replay=False):
        self.status = status
        self.replay = replay
        self.calls = []
        self.previous = {}
        self.stock = 10

    def receive_order(self, *, actor_id, order_id, idempotency_key, receipt):
        self.calls.append((actor_id, order_id, idempotency_key, receipt))
        previous = self.previous.get(idempotency_key)
        if previous:
            if previous[0] != receipt.request_hash:
                raise PurchaseOrderConflict("La clave de idempotencia ya se usó con otros datos.")
            return previous[1], True
        if self.status not in {"ISSUED", "PARTIALLY_RECEIVED"}:
            raise PurchaseOrderConflict("Solo se reciben órdenes emitidas y no canceladas.")
        items = []
        for line_id, quantity in receipt.items:
            movement = None
            if line_id == 1:
                movement = {
                    "id": 91, "quantity_delta": quantity, "stock_before": self.stock,
                    "stock_after": self.stock + quantity,
                }
                self.stock += quantity
            items.append({
                "purchase_order_item_id": line_id,
                "quantity_received": str(quantity),
                "movement": movement,
            })
        self.receipt = {
            "id": 501,
            "purchase_order_id": order_id,
            "received_by": actor_id,
            "received_at": "2026-11-09T11:00:00+00:00",
            "notes": receipt.notes,
            "items": items,
        }
        self.previous[idempotency_key] = (receipt.request_hash, self.receipt)
        self.status = "PARTIALLY_RECEIVED"
        return self.receipt, self.replay

    def list_receipts(self, order_id):
        return [self.receipt] if order_id == 31 and hasattr(self, "receipt") else ([] if order_id == 31 else None)


def client_for(repository):
    def require_admin():
        return SessionCustomer(8, "Ana", "Admin", "admin@example.test", "ADMIN")

    app = FastAPI()
    app.include_router(create_purchase_order_router(
        require_admin=require_admin,
        repository_factory=lambda: repository,
    ))
    return TestClient(app)


def test_receipt_requires_idempotency_key_and_positive_integer_lines():
    repository = ReceiptRepository()
    client = client_for(repository)
    payload = {"items": [{"purchase_order_item_id": 1, "quantity_received": 4}]}
    missing_key = client.post("/api/admin/purchase-orders/31/receipts", json=payload)
    invalid_quantity = client.post("/api/admin/purchase-orders/31/receipts", headers={
        "Idempotency-Key": "84c55cf2-22aa-4e23-94d8-a5cb1393d105",
    }, json={"items": [{"purchase_order_item_id": 1, "quantity_received": 0}]})
    assert missing_key.status_code == 422
    assert invalid_quantity.status_code == 422
    assert repository.calls == []


def test_order_receipt_returns_created_then_idempotent_replay():
    payload = {"items": [{"purchase_order_item_id": 1, "quantity_received": 4}]}
    headers = {"Idempotency-Key": "84c55cf2-22aa-4e23-94d8-a5cb1393d105"}
    created_repo = ReceiptRepository()
    created = client_for(created_repo).post(
        "/api/admin/purchase-orders/31/receipts", headers=headers, json=payload
    )
    replay = client_for(created_repo).post(
        "/api/admin/purchase-orders/31/receipts", headers=headers, json=payload
    )
    assert created.status_code == 201
    assert created.json()["receipt"]["items"][0]["movement"]["stock_after"] == 14
    assert replay.status_code == 200
    assert replay.headers["Idempotent-Replayed"] == "true"
    assert created_repo.stock == 14
    assert len(created_repo.calls) == 2


def test_free_text_receipt_has_no_stock_movement_and_changed_key_payload_conflicts():
    repository = ReceiptRepository()
    client = client_for(repository)
    headers = {"Idempotency-Key": "84c55cf2-22aa-4e23-94d8-a5cb1393d105"}
    free_text = {"items": [{"purchase_order_item_id": 2, "quantity_received": 1}]}
    accepted = client.post("/api/admin/purchase-orders/31/receipts", headers=headers, json=free_text)
    changed = client.post("/api/admin/purchase-orders/31/receipts", headers=headers, json={
        "notes": "different content",
        "items": [{"purchase_order_item_id": 2, "quantity_received": 1}],
    })
    assert accepted.status_code == 201
    assert accepted.json()["receipt"]["items"][0]["movement"] is None
    assert changed.status_code == 409
    assert repository.stock == 10


def test_draft_order_cannot_be_received():
    repository = ReceiptRepository(status="DRAFT")
    response = client_for(repository).post(
        "/api/admin/purchase-orders/31/receipts",
        headers={"Idempotency-Key": "84c55cf2-22aa-4e23-94d8-a5cb1393d105"},
        json={"items": [{"purchase_order_item_id": 1, "quantity_received": 1}]},
    )
    assert response.status_code == 409
    assert repository.stock == 10


def test_order_receipt_history_is_available():
    client = client_for(ReceiptRepository())
    client.post("/api/admin/purchase-orders/31/receipts", headers={
        "Idempotency-Key": "84c55cf2-22aa-4e23-94d8-a5cb1393d105",
    }, json={"items": [{"purchase_order_item_id": 1, "quantity_received": 1}]})
    response = client.get("/api/admin/purchase-orders/31/receipts")
    assert response.status_code == 200
    assert response.json()["items"][0]["id"] == 501


def test_purchase_order_migration_schema_is_present(purchase_order_test_engine):
    inspector = inspect(purchase_order_test_engine)
    tables = set(inspector.get_table_names(schema="public"))
    assert {"purchase_order_receipts", "purchase_order_receipt_items", "purchase_order_audit_events"} <= tables
    assert "purchase_order_receipt_item_id" in {
        column["name"] for column in inspector.get_columns("inventory_movements", schema="public")
    }
    assert "purchase_order_item_id" in {
        column["name"] for column in inspector.get_columns("supplier_purchase_items", schema="public")
    }
