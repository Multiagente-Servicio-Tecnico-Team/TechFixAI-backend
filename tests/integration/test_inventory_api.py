from contextlib import nullcontext
from decimal import Decimal
import sqlite3

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.accounts.config import Settings as AccountSettings
from app.accounts.models import Base, Role, User
from app.accounts.security import hash_password, password_fingerprint, sign_session
from app.accounts.session import SessionGuard
from app.adapters.patterns.registry import PATTERN_NAMES
from app.infrastructure.chat_app import build_chat_app
from app.settings import Settings

PASSWORD = "InventoryTest#2026"
AUTH = AccountSettings(
    database_url=None,
    auth_secret="i" * 48,
    secure_cookie=False,
    frontend_origins=("http://localhost:5174",),
    bcrypt_rounds=4,
)
CHAT_SETTINGS = Settings(
    None, None, None, None, False, "tests", True, True, Decimal("35"), Decimal("50")
)
sqlite3.register_adapter(Decimal, lambda value: format(value, ".2f"))


class FakeGraph:
    def invoke(self, *_args, **_kwargs):
        return {"messages": []}


@pytest.fixture
def inventory_client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as db:
        db.add_all([
            User(email="customer@test.pe", phone="+51900000001", password_hash=hash_password(PASSWORD, 4),
                 name="Cliente", role=Role.CUSTOMER),
            User(email="tech@test.pe", phone="+51900000002", password_hash=hash_password(PASSWORD, 4),
                 name="Técnico", role=Role.TECHNICIAN),
            User(email="admin@test.pe", phone="+51900000003", password_hash=hash_password(PASSWORD, 4),
                 name="Admin", role=Role.ADMIN),
        ])
        db.commit()
    with engine.begin() as connection:
        connection.exec_driver_sql("""CREATE TABLE spare_parts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code VARCHAR(50) NOT NULL UNIQUE,
            name VARCHAR(150) NOT NULL,
            category VARCHAR(50),
            description TEXT,
            unit_price NUMERIC(10,2) NOT NULL CHECK (unit_price >= 0),
            current_stock INTEGER NOT NULL DEFAULT 0 CHECK (current_stock >= 0),
            minimum_threshold INTEGER NOT NULL DEFAULT 5 CHECK (minimum_threshold >= 0),
            active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")
        connection.exec_driver_sql("""CREATE TRIGGER trg_spare_parts_updated_at
            AFTER UPDATE ON spare_parts
            BEGIN UPDATE spare_parts SET updated_at=CURRENT_TIMESTAMP WHERE id=NEW.id; END""")
        connection.exec_driver_sql("""CREATE TABLE quote_details (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            spare_part_id INTEGER NOT NULL REFERENCES spare_parts(id) ON DELETE RESTRICT
        )""")
        connection.exec_driver_sql("""CREATE TABLE purchase_order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            spare_part_id INTEGER REFERENCES spare_parts(id) ON DELETE SET NULL
        )""")

    guard = SessionGuard(AUTH, factory)
    repository_factory = lambda: __import__(
        "app.adapters.persistence.inventory", fromlist=["InventoryRepositoryAdapter"]
    ).InventoryRepositoryAdapter(factory)
    application = build_chat_app(
        session_guard=guard,
        graph_factories={name: FakeGraph for name in PATTERN_NAMES},
        settings_factory=lambda: CHAT_SETTINGS,
        trace_context_factory=nullcontext,
        inventory_repository_factory=repository_factory,
    )
    client = TestClient(application)
    with factory() as db:
        users = {user.role.value: user for user in db.query(User).all()}
    yield client, users, factory, engine
    engine.dispose()


def authorize(client, user):
    fingerprint = password_fingerprint(user.password_hash, AUTH.auth_secret)
    client.cookies.set(
        AUTH.cookie_name,
        sign_session(user.id, AUTH.auth_secret, 3600, fingerprint),
    )


def create_part_payload(code="RAM-DDR4-16", **overrides):
    payload = {
        "code": code,
        "name": "Memoria RAM DDR4 16 GB",
        "category": "RAM Desktop",
        "description": "UDIMM",
        "unit_price": "95.00",
        "current_stock": 4,
        "minimum_threshold": 1,
    }
    payload.update(overrides)
    return payload


def test_list_categories_and_staff_authorization(inventory_client):
    client, users, factory, _engine = inventory_client
    with factory() as db:
        db.execute(text("""INSERT INTO spare_parts
            (code,name,category,description,unit_price,current_stock,minimum_threshold,active)
            VALUES ('RAM-1','RAM DDR4','RAM Desktop','UDIMM',95.00,4,1,TRUE),
                   ('RAM-2','RAM Laptop','RAM Laptop','SODIMM',48.00,2,1,TRUE),
                   ('OFF-1','Inactivo','GPU','',10.00,0,0,FALSE)"""))
        db.commit()

    assert client.get("/api/inventory/parts").status_code == 401
    authorize(client, users[Role.CUSTOMER.value])
    assert client.get("/api/inventory/parts").json()["code"] == "staff_only"

    authorize(client, users[Role.TECHNICIAN.value])
    parts = client.get("/api/inventory/parts")
    categories = client.get("/api/inventory/categories")
    assert parts.status_code == 200
    assert [part["code"] for part in parts.json()["parts"]] == ["RAM-1", "RAM-2"]
    assert categories.json() == {"categories": ["RAM Desktop", "RAM Laptop"]}

    authorize(client, users[Role.ADMIN.value])
    assert client.get("/api/inventory/categories").status_code == 200


def test_create_duplicate_invalid_and_list_round_trip(inventory_client):
    client, users, _factory, _engine = inventory_client
    authorize(client, users[Role.ADMIN.value])

    created = client.post("/api/inventory/parts", json=create_part_payload())
    assert created.status_code == 201
    assert created.json()["part"]["unit_price"] == "95.00"
    assert created.json()["part"]["active"] is True
    assert client.get("/api/inventory/parts").json()["parts"][0]["code"] == "RAM-DDR4-16"

    duplicate = client.post("/api/inventory/parts", json=create_part_payload())
    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == "duplicate"

    invalid = client.post("/api/inventory/parts", json=create_part_payload(code="bad sku"))
    assert invalid.status_code == 422
    assert invalid.json()["code"] == "invalid"
    assert invalid.json()["field"] == "code"


def test_update_preserves_code_and_delete_respects_quote_fk(inventory_client):
    client, users, factory, _engine = inventory_client
    authorize(client, users[Role.TECHNICIAN.value])
    created = client.post("/api/inventory/parts", json=create_part_payload("RAM-HIST"))
    assert created.status_code == 201
    with factory() as db:
        db.execute(text("UPDATE spare_parts SET updated_at='2000-01-01 00:00:00' WHERE code='RAM-HIST'"))
        db.commit()

    updated = client.put(
        "/api/inventory/parts/RAM-HIST",
        json=create_part_payload("RAM-HIST", name="Memoria RAM actualizada", current_stock=2, unit_price="99.90"),
    )
    assert updated.status_code == 200
    assert updated.json()["part"]["code"] == "RAM-HIST"
    assert updated.json()["part"]["name"] == "Memoria RAM actualizada"
    assert updated.json()["part"]["unit_price"] == "99.90"
    assert updated.json()["part"]["updated_at"] != "2000-01-01T00:00:00"

    assert client.put("/api/inventory/parts/MISSING", json=create_part_payload("MISSING")).status_code == 404
    assert client.put(
        "/api/inventory/parts/RAM-HIST",
        json=create_part_payload("OTHER-CODE"),
    ).status_code == 422

    with factory() as db:
        part_id = db.execute(text("SELECT id FROM spare_parts WHERE code='RAM-HIST'")).scalar_one()
        db.execute(text("INSERT INTO quote_details(spare_part_id) VALUES (:id)"), {"id": part_id})
        db.commit()
    blocked = client.delete("/api/inventory/parts/RAM-HIST")
    assert blocked.status_code == 409
    assert blocked.json()["code"] == "in_use"

    with factory() as db:
        db.execute(text("DELETE FROM quote_details"))
        db.commit()
    assert client.delete("/api/inventory/parts/RAM-HIST").status_code == 204
    assert client.delete("/api/inventory/parts/RAM-HIST").status_code == 404


def test_inventory_put_cors_preflight_allows_frontend_origin(inventory_client):
    client, _users, _factory, _engine = inventory_client
    response = client.options(
        "/api/inventory/parts/RAM-1",
        headers={
            "Origin": "http://localhost:5174",
            "Access-Control-Request-Method": "PUT",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert response.status_code == 200
    assert "PUT" in response.headers["access-control-allow-methods"]
    assert response.headers["access-control-allow-origin"] == "http://localhost:5174"
