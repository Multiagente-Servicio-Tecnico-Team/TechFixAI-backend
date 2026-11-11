"""GET /api/admin/suppliers/{id}: consulta de un proveedor para editarlo desde el panel."""
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.adapters.api.purchases import create_supplier_purchase_router
from app.adapters.persistence.purchases import SupplierPurchaseRepositoryAdapter
from app.application.errors import SupplierNotFound
from app.application.purchases import SupplierPurchaseService

SUPPLIER = {
    "id": 7, "name": "Distribuidora Tech", "tax_id": "20601234567", "contact_name": "Ana Torres",
    "contact_email": "ventas@tech.pe", "phone": "+51 999 111 222", "address": None,
    "delivery_lead_days": 3, "active": False, "created_at": "2026-11-04T10:00:00",
}


class FakeRepository:
    def __init__(self, error=None):
        self.error = error
        self.calls = []

    def get_supplier(self, supplier_id):
        self.calls.append(supplier_id)
        if self.error:
            raise self.error
        return dict(SUPPLIER) if supplier_id == SUPPLIER["id"] else None


def client_for(repository, *, admin=True):
    def require_admin():
        if not admin:
            raise HTTPException(status_code=403, detail="Solo administradores.")
        return object()

    app = FastAPI()
    app.include_router(create_supplier_purchase_router(require_admin=require_admin, repository_factory=lambda: repository))
    return TestClient(app)


def test_returns_supplier_even_when_inactive():
    repository = FakeRepository()
    response = client_for(repository).get("/api/admin/suppliers/7")
    assert response.status_code == 200
    assert response.json() == {"supplier": SUPPLIER}
    assert repository.calls == [7]


def test_unknown_supplier_returns_404():
    response = client_for(FakeRepository()).get("/api/admin/suppliers/99")
    assert response.status_code == 404
    assert response.json()["code"] == "supplier_not_found"


def test_non_positive_id_is_rejected_without_querying():
    repository = FakeRepository()
    response = client_for(repository).get("/api/admin/suppliers/0")
    assert response.status_code == 422
    assert response.json()["field"] == "supplier_id"
    assert repository.calls == []


def test_requires_admin():
    repository = FakeRepository()
    response = client_for(repository, admin=False).get("/api/admin/suppliers/7")
    assert response.status_code == 403
    assert repository.calls == []


def test_storage_failure_returns_503_without_details():
    error = OperationalError("SELECT secret", {}, Exception("connection refused"))
    response = client_for(FakeRepository(error=error)).get("/api/admin/suppliers/7")
    assert response.status_code == 503
    assert "secret" not in response.text and "refused" not in response.text


def test_service_raises_not_found():
    with pytest.raises(SupplierNotFound):
        SupplierPurchaseService(FakeRepository()).get_supplier(5)


def test_adapter_reads_supplier_by_id():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    with engine.begin() as connection:
        connection.execute(text("""CREATE TABLE suppliers (
            id INTEGER PRIMARY KEY, name TEXT NOT NULL, tax_id TEXT, contact_name TEXT, contact_email TEXT,
            phone TEXT, address TEXT, delivery_lead_days INTEGER, active BOOLEAN NOT NULL,
            created_at TEXT)"""))
        connection.execute(text("""INSERT INTO suppliers VALUES
            (3, 'Repuestos Norte', NULL, NULL, NULL, NULL, NULL, NULL, 0, '2026-11-04T09:00:00')"""))
    adapter = SupplierPurchaseRepositoryAdapter(sessionmaker(bind=engine))
    assert adapter.get_supplier(3) == {
        "id": 3, "name": "Repuestos Norte", "tax_id": None, "contact_name": None, "contact_email": None,
        "phone": None, "address": None, "delivery_lead_days": None, "active": False,
        "created_at": "2026-11-04T09:00:00",
    }
    assert adapter.get_supplier(4) is None
