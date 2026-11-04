from contextlib import nullcontext
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.accounts.api import create_app as create_accounts_app
from app.accounts.config import Settings as AccountSettings
from app.accounts.models import Base, Role, User
from app.accounts.security import hash_password
from app.accounts.session import SessionGuard
from app.application.errors import AccountingConflict
from app.application.errors import AccountingStorageUnavailable
from app.domain.accounting import AccountingValidationError
from app.adapters.patterns.registry import PATTERN_NAMES
from app.main import create_app
from app.settings import Settings

PASSWORD = "AccountingTest#2026"
ACCOUNT_SETTINGS = AccountSettings(database_url=None, auth_secret="a" * 48, secure_cookie=False, bcrypt_rounds=4)


class FakeGraph:
    def get_state(self, _config):
        from types import SimpleNamespace
        return SimpleNamespace(values={})

    def invoke(self, *_args, **_kwargs):
        from langchain_core.messages import AIMessage
        return {"messages": [AIMessage(content="Consulta recibida.")]}


class FakeAccountingRepository:
    def __init__(self):
        self.entries = {}
        self.keys = {}
        self.next_id = 1
        self.fail_category_read = False
        self.fail_create = False
        self.category_active = True
        self.reversal_calls = []

    def list_categories(self):
        if self.fail_category_read:
            raise AccountingStorageUnavailable()
        return ([{"id": 1, "code": "SALE", "name": "Venta", "description": None}]
                if self.category_active else [])

    def create_entry(self, actor, key, digest, draft):
        if self.fail_create:
            raise AccountingStorageUnavailable()
        if not self.category_active or draft.draft.category_id != 1:
            raise AccountingValidationError("La categoría no está disponible.")
        prior = self.keys.get((actor, key))
        if prior:
            if prior[0] != digest:
                raise AccountingConflict("La clave de idempotencia ya se usó con otros datos.")
            return prior[1], True
        identifier = self.next_id
        self.next_id += 1
        entry = self._entry(identifier, actor, draft)
        self.keys[(actor, key)] = (digest, entry)
        self.entries[identifier] = entry
        return entry, False

    @staticmethod
    def _entry(identifier, actor, draft):
        return {
            "id": identifier, "entry_number": str(identifier), "operation_date": draft.draft.operation_date.isoformat(),
            "concept": draft.draft.concept, "detail": draft.draft.detail,
            "category": {"id": 1, "code": "SALE", "name": "Venta", "description": None},
            "currency": "PEN", "debit_total": f"{draft.debit_total:.2f}", "credit_total": f"{draft.credit_total:.2f}",
            "amount": f"{draft.debit_total:.2f}", "status": "CONFIRMED",
            "responsible": {"user_id": actor, "display_name": "Ana Admin"},
            "created_at": datetime.now(timezone.utc).isoformat(), "updated_at": datetime.now(timezone.utc).isoformat(), "reversed_at": None,
            "reversal_of_entry_id": None, "reversal_entry_id": None,
            "lines": [{"line_number": i, "account_code": line.account_code, "account_name": line.account_name,
                       "description": line.description, "debit": f"{line.debit:.2f}", "credit": f"{line.credit:.2f}"}
                      for i, line in enumerate(draft.draft.lines, 1)],
            "audit_events": [{"event_type": "ENTRY_CREATED", "actor": {"user_id": actor, "display_name": "Ana Admin"},
                              "related_entry_id": None, "reason": None, "created_at": datetime.now(timezone.utc).isoformat()}],
        }

    def list_entries(self, **filters):
        items = list(self.entries.values())
        if filters.get("category_id") is not None:
            items = [item for item in items if item["category"]["id"] == filters["category_id"]]
        if filters.get("status"):
            items = [item for item in items if item["status"] == filters["status"]]
        if filters.get("entry_number") is not None:
            items = [item for item in items if int(item["entry_number"]) == filters["entry_number"]]
        if filters.get("from_date"):
            items = [item for item in items if item["operation_date"] >= filters["from_date"].isoformat()]
        if filters.get("to_date"):
            items = [item for item in items if item["operation_date"] <= filters["to_date"].isoformat()]
        return {"items": items[filters["offset"]:filters["offset"] + filters["limit"]], "total": len(items),
                "limit": filters["limit"], "offset": filters["offset"]}

    def get_entry(self, entry_id):
        return self.entries.get(entry_id)

    def reverse_entry(self, actor_id, entry_id, operation_date, reason):
        self.reversal_calls.append((actor_id, entry_id, operation_date, reason))
        original = self.entries.get(entry_id)
        if original is None:
            from app.application.errors import AccountingNotFound
            raise AccountingNotFound()
        from app.application.errors import AccountingConflict
        if original["status"] == "REVERSED":
            previous = self.entries[original["reversal_entry_id"]]
            if previous["operation_date"] == operation_date.isoformat() and previous["reversal_reason"] == reason:
                return {"original": original, "reversal": previous}, True
            raise AccountingConflict()
        original["status"] = "REVERSED"
        reversal = dict(original)
        reversal.update({"id": self.next_id, "entry_number": str(self.next_id), "operation_date": operation_date.isoformat(),
                         "status": "CONFIRMED", "reversal_of_entry_id": entry_id, "reversal_entry_id": None,
                         "reversal_reason": reason,
                         "debit_total": original["credit_total"], "credit_total": original["debit_total"],
                         "amount": original["debit_total"],
                         "lines": [{**line, "debit": line["credit"], "credit": line["debit"]} for line in original["lines"]]})
        self.next_id += 1
        original["reversal_entry_id"] = reversal["id"]
        self.entries[reversal["id"]] = reversal
        return {"original": original, "reversal": reversal}, False


@pytest.fixture
def accounting_client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    accounts = TestClient(create_accounts_app(ACCOUNT_SETTINGS, factory))
    accounts.post("/registro", json={"nombre": "Cliente Demo", "email": "cliente@test.pe", "telefono": "+51900000001", "password": PASSWORD})
    with factory() as db:
        db.add(User(email="admin@test.pe", phone="+51900000002", password_hash=hash_password(PASSWORD, 4), name="Ana", last_name="Admin", role=Role.ADMIN))
        db.add(User(email="technician@test.pe", phone="+51900000003", password_hash=hash_password(PASSWORD, 4), name="Técnico", role=Role.TECHNICIAN))
        db.commit()
    settings = Settings(None, None, None, None, False, "tests", True, True, Decimal("35"), Decimal("50"))
    repository = FakeAccountingRepository()
    app = create_app(
        session_guard=SessionGuard(ACCOUNT_SETTINGS, factory),
        graph_factories={name: FakeGraph for name in PATTERN_NAMES},
        settings_factory=lambda: settings,
        trace_context_factory=nullcontext,
        accounting_repository_factory=lambda: repository,
    )
    client = TestClient(app)
    client.post("/auth/login", json={"email": "admin@test.pe", "password": PASSWORD})
    yield client, accounts, repository
    engine.dispose()


def payload(concept="Venta mostrador"):
    return {"operation_date": "2026-11-02", "concept": concept, "detail": "Registro interno", "category_id": 1,
            "lines": [{"account_code": "101", "account_name": "Caja", "description": None, "debit": "100.00", "credit": "0.00"},
                      {"account_code": "701", "account_name": "Ventas", "description": None, "debit": "0.00", "credit": "100.00"}]}


def test_accounting_chat_requires_signed_admin_and_does_not_write(accounting_client):
    client, _, repository = accounting_client
    request = {"pattern": "decentralized", "message": "categorías contables"}
    response = client.post("/api/chat", json=request)
    assert response.status_code == 200
    assert client.post("/api/chat", json={"pattern": "decentralized", "message": "confirmar asiento",
                                           "action": "accept_quote"}).status_code == 403
    assert client.post("/api/chat", json={"pattern": "decentralized",
                                           "message": '{"operation_date":"2026-11-03","lines":[]}'}).status_code == 409
    assert repository.entries == {}

    client.post("/auth/logout")
    assert client.post("/api/chat", json=request).status_code == 401
    client.post("/auth/login", json={"email": "cliente@test.pe", "password": PASSWORD})
    assert client.post("/api/chat", json={**request, "role": "ADMIN"}).status_code == 403
    client.post("/auth/login", json={"email": "technician@test.pe", "password": PASSWORD})
    assert client.post("/api/chat", json=request).status_code == 403
    assert repository.entries == {}


def test_create_replay_conflict_and_detail(accounting_client):
    client, _, _ = accounting_client
    key = "723d06c0-65da-4d2c-8471-b8d71d28771c"
    created = client.post("/api/admin/accounting/entries", headers={"Idempotency-Key": key}, json=payload())
    assert created.status_code == 201
    assert created.json()["responsible"]["user_id"] == 2
    replay = client.post("/api/admin/accounting/entries", headers={"Idempotency-Key": key}, json=payload())
    assert replay.status_code == 200
    assert replay.headers["Idempotent-Replayed"] == "true"
    conflict = client.post("/api/admin/accounting/entries", headers={"Idempotency-Key": key}, json=payload("Otro concepto"))
    assert conflict.status_code == 409
    detail = client.get("/api/admin/accounting/entries/1")
    assert detail.json()["detail"] == "Registro interno"
    assert [line["line_number"] for line in detail.json()["lines"]] == [1, 2]
    assert detail.json()["audit_events"][0]["event_type"] == "ENTRY_CREATED"
    assert detail.headers["cache-control"] == "no-store"


def test_admin_only_and_input_balance_validation(accounting_client):
    client, accounts, repository = accounting_client
    assert client.get("/api/admin/accounting/categories").status_code == 200
    client.cookies.clear()
    assert client.get("/api/admin/accounting/categories").status_code == 401
    accounts.post("/login", json={"email": "cliente@test.pe", "password": PASSWORD})
    client.cookies.set("techfix_session", accounts.cookies.get("techfix_session"))
    assert client.get("/api/admin/accounting/entries").status_code == 403
    accounts.post("/login", json={"email": "technician@test.pe", "password": PASSWORD})
    client.cookies.set("techfix_session", accounts.cookies.get("techfix_session"))
    assert client.get("/api/admin/accounting/categories").status_code == 403
    invalid = payload()
    invalid["lines"][1]["credit"] = "99.99"
    client.post("/auth/login", json={"email": "admin@test.pe", "password": PASSWORD})
    result = client.post("/api/admin/accounting/entries", headers={"Idempotency-Key": "fd2e141d-885d-44f2-8a7b-885221bf94f0"}, json=invalid)
    assert result.status_code == 422
    assert result.json()["code"] == "accounting_validation"
    repository.category_active = False
    inactive = client.post("/api/admin/accounting/entries", headers={"Idempotency-Key": "1cdb4bec-77d8-4e70-8fb0-6ca662859232"}, json=payload())
    assert inactive.status_code == 422
    repository.category_active = True
    repository.fail_create = True
    unavailable = client.post("/api/admin/accounting/entries", headers={"Idempotency-Key": "fafc78c4-6fd8-4ddb-bc84-8eeb0cb911d5"}, json=payload())
    assert unavailable.status_code == 503
    assert not repository.entries
    repository.fail_create = False
    repository.fail_category_read = True
    assert client.get("/api/admin/accounting/categories").status_code == 503


def test_cors_allows_accounting_idempotency_header(accounting_client):
    client, _, _ = accounting_client
    response = client.options(
        "/api/admin/accounting/entries",
        headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST",
                 "Access-Control-Request-Headers": "content-type,idempotency-key"},
    )
    assert response.status_code == 200
    assert "Idempotency-Key" in response.headers["access-control-allow-headers"]


def test_listing_reversal_and_not_found(accounting_client):
    client, _, _ = accounting_client
    created = client.post("/api/admin/accounting/entries", headers={"Idempotency-Key": "723d06c0-65da-4d2c-8471-b8d71d28771c"}, json=payload())
    assert created.status_code == 201
    listed = client.get("/api/admin/accounting/entries?from_date=2026-11-01&to_date=2026-11-30&category_id=1&status=CONFIRMED&entry_number=1&limit=10&offset=0")
    assert listed.json()["total"] == 1
    assert client.get("/api/admin/accounting/entries/999").status_code == 404
    reversal = client.post("/api/admin/accounting/entries/1/reverse", json={"operation_date": "2026-11-03", "reason": "Anulación"})
    assert reversal.status_code == 201
    assert reversal.json()["reversal"]["reversal_of_entry_id"] == 1
    assert client.get("/api/admin/accounting/entries?status=REVERSED").json()["total"] == 1
    assert client.post("/api/admin/accounting/entries/999/reverse", json={"operation_date": "2026-11-03", "reason": "No existe"}).status_code == 404


def test_reversal_requires_admin_and_delegates_actor_and_replay_to_003(accounting_client):
    client, _, repository = accounting_client
    created = client.post("/api/admin/accounting/entries",
                          headers={"Idempotency-Key": "723d06c0-65da-4d2c-8471-b8d71d28771c"}, json=payload())
    assert created.status_code == 201
    original_lines = created.json()["lines"]
    path = "/api/admin/accounting/entries/1/reverse"
    body = {"operation_date": "2026-11-03", "reason": "Corrección manual"}

    client.post("/auth/logout")
    assert client.post(path, json=body).status_code == 401
    client.post("/auth/login", json={"email": "cliente@test.pe", "password": PASSWORD})
    assert client.post(path, json=body).status_code == 403
    client.post("/auth/login", json={"email": "technician@test.pe", "password": PASSWORD})
    assert client.post(path, json=body).status_code == 403
    assert repository.reversal_calls == []

    client.post("/auth/login", json={"email": "admin@test.pe", "password": PASSWORD})
    assert client.post(path, json={**body, "actor_id": 999}).status_code == 422
    assert repository.reversal_calls == []
    reversed_response = client.post(path, json=body)
    assert reversed_response.status_code == 201
    assert repository.reversal_calls == [(2, 1, date(2026, 11, 3), "Corrección manual")]
    assert reversed_response.json()["reversal"]["reversal_of_entry_id"] == 1
    assert client.get("/api/admin/accounting/entries/1").json()["lines"] == original_lines

    replay = client.post(path, json=body)
    assert replay.status_code == 200
    assert len(repository.entries) == 2
    assert client.post(path, json={**body, "reason": "Otro motivo"}).status_code == 409
    assert len(repository.entries) == 2
