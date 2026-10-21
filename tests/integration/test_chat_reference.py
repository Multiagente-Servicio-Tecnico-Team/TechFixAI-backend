"""Pruebas del contrato POST /api/chat con el patrón de referencia y la sesión del login."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.accounts.api import create_app
from app.accounts.config import Settings
from app.accounts.models import Base, Role, User
from app.accounts.security import hash_password
from app.chat.models import Ticket
from app.chat.reference import create_reference_app

PASSWORD = "TriageTech#2026"
SETTINGS = Settings(database_url=None, auth_secret="s" * 48, secure_cookie=False, bcrypt_rounds=4)
PROBLEM = "Mi laptop HP no detecta el disco SSD desde ayer"


@pytest.fixture()
def env():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    accounts = TestClient(create_app(SETTINGS, factory))
    for email in ("ana@demo.pe", "luis@demo.pe"):
        accounts.post("/registro", json={"nombre": "Ana Torres", "email": email, "telefono": "+51987654321", "password": PASSWORD})
    with factory() as db:
        db.add(User(email="tecnico@taller.com", phone="+51911111111", password_hash=hash_password(PASSWORD, 4), name="Carlos", role=Role.TECHNICIAN))
        db.commit()
    return accounts, create_reference_app(SETTINGS, factory), factory


def chat_client(accounts, app, email):
    accounts.cookies.clear()
    accounts.post("/login", json={"email": email, "password": PASSWORD})
    client = TestClient(app)
    client.cookies.set("techfix_session", accounts.cookies.get("techfix_session"))
    return client


def tickets(factory):
    with factory() as db:
        return db.scalars(select(Ticket)).all()


def test_without_session_401(env):
    _, app, _ = env
    res = TestClient(app).post("/api/chat", json={"message": PROBLEM})
    assert res.status_code == 401 and res.json()["code"] == "session_required"


def test_technician_403(env):
    accounts, app, _ = env
    res = chat_client(accounts, app, "tecnico@taller.com").post("/api/chat", json={"message": PROBLEM})
    assert res.status_code == 403


def test_asks_for_details_when_message_is_short(env):
    accounts, app, factory = env
    res = chat_client(accounts, app, "ana@demo.pe").post("/api/chat", json={"message": "hola"})
    body = res.json()
    assert res.status_code == 200 and "Hola Ana" in body["reply"] and body["conversation_id"]
    assert "quote" not in body and tickets(factory) == []


def test_quote_and_ticket_belong_to_session_customer(env):
    accounts, app, factory = env
    client = chat_client(accounts, app, "ana@demo.pe")
    # Un correo o customer_id en el cuerpo no cambia al cliente identificado.
    res = client.post("/api/chat", json={"message": PROBLEM, "email": "luis@demo.pe", "customer_id": 2})
    body = res.json()

    assert res.status_code == 200
    assert body["quote"] == {"status": "proposed", "currency": "PEN", "total": "260.00",
                             "lines": [{"label": "Instalación de SSD", "amount": "80.00"}, {"label": "SSD de 480 GB", "amount": "180.00"}]}
    assert body["ticket"]["status"] == "QUOTED" and body["ticket"]["code"].startswith("TCK-")
    [ticket] = tickets(factory)
    assert ticket.customer_id == 1 and ticket.failure_description == PROBLEM


def test_accept_and_reject(env):
    accounts, app, factory = env
    client = chat_client(accounts, app, "ana@demo.pe")
    conv = client.post("/api/chat", json={"message": PROBLEM}).json()["conversation_id"]

    accepted = client.post("/api/chat", json={"conversation_id": conv, "action": "accept_quote"}).json()
    assert accepted["quote"]["status"] == "confirmed" and accepted["ticket"]["status"] == "IN_REPAIR"
    assert tickets(factory)[0].status.value == "IN_REPAIR"
    again = client.post("/api/chat", json={"conversation_id": conv, "action": "accept_quote"})
    assert again.status_code == 409

    conv2 = client.post("/api/chat", json={"message": "La pantalla de mi laptop parpadea mucho"}).json()["conversation_id"]
    rejected = client.post("/api/chat", json={"conversation_id": conv2, "action": "reject_quote"}).json()
    assert rejected["quote"]["status"] == "rejected" and rejected["ticket"]["status"] == "CANCELLED"


def test_other_customer_conversation_404(env):
    accounts, app, _ = env
    conv = chat_client(accounts, app, "ana@demo.pe").post("/api/chat", json={"message": PROBLEM}).json()["conversation_id"]
    res = chat_client(accounts, app, "luis@demo.pe").post("/api/chat", json={"conversation_id": conv, "action": "accept_quote"})
    assert res.status_code == 404


def test_invalid_body_does_not_echo_message(env):
    accounts, app, _ = env
    client = chat_client(accounts, app, "ana@demo.pe")
    assert client.post("/api/chat", json={"message": "   "}).status_code == 422
    res = client.post("/api/chat", json={"message": "x" * 2001})
    assert res.status_code == 422 and "x" * 50 not in res.text


def test_message_limit(env):
    accounts, app, _ = env
    client = chat_client(accounts, app, "ana@demo.pe")
    for _ in range(20):
        assert client.post("/api/chat", json={"message": "hola"}).status_code == 200
    assert client.post("/api/chat", json={"message": "hola"}).status_code == 429
