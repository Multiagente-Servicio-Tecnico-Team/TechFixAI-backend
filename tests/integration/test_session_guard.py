"""Pruebas de la dependencia de sesión reutilizable (SessionGuard)."""
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, update
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.accounts.api import create_app
from app.accounts.config import Settings
from app.accounts.models import Base, Role, User
from app.accounts.security import hash_password, sign_session
from app.accounts.session import SessionGuard

PASSWORD = "TriageTech#2026"
SETTINGS = Settings(database_url=None, auth_secret="s" * 48, secure_cookie=False, bcrypt_rounds=4)


@pytest.fixture()
def env():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    accounts = TestClient(create_app(SETTINGS, factory))
    accounts.post("/registro", json={"nombre": "Ana Torres", "email": "ana@demo.pe", "telefono": "+51987654321", "password": PASSWORD})
    with factory() as db:
        db.add(User(email="tecnico@taller.com", phone="+51911111111", password_hash=hash_password(PASSWORD, 4), name="Carlos", role=Role.TECHNICIAN))
        db.commit()

    guard = SessionGuard(SETTINGS, factory)
    other = FastAPI()
    guard.install(other)

    @other.get("/customer")
    def customer_route(customer=Depends(guard.require_customer)):
        return {"id": customer.id, "email": customer.email, "role": customer.role}

    @other.get("/user")
    def user_route(user=Depends(guard.require_user)):
        return {"role": user.role}

    return accounts, TestClient(other), factory


def login(accounts, email):
    assert accounts.post("/login", json={"email": email, "password": PASSWORD}).status_code == 200
    return accounts.cookies.get("techfix_session")


def test_customer_with_session(env):
    accounts, other, _ = env
    other.cookies.set("techfix_session", login(accounts, "ana@demo.pe"))
    assert other.get("/customer").json() == {"id": 1, "email": "ana@demo.pe", "role": "CUSTOMER"}


def test_missing_or_tampered_cookie(env):
    _, other, _ = env
    res = other.get("/customer")
    assert res.status_code == 401 and res.json() == {"detail": "Inicia sesión para continuar.", "code": "session_required"}
    other.cookies.set("techfix_session", sign_session(1, "otro-secreto" * 4, 3600))
    assert other.get("/customer").status_code == 401


def test_expired_cookie(env):
    _, other, _ = env
    other.cookies.set("techfix_session", sign_session(1, SETTINGS.auth_secret, -10))
    assert other.get("/customer").status_code == 401


def test_inactive_account(env):
    accounts, other, factory = env
    other.cookies.set("techfix_session", login(accounts, "ana@demo.pe"))
    with factory() as db:
        db.execute(update(User).values(active=False))
        db.commit()
    assert other.get("/customer").status_code == 401


def test_changed_password_invalidates_session(env):
    accounts, other, factory = env
    other.cookies.set("techfix_session", login(accounts, "ana@demo.pe"))
    with factory() as db:
        db.execute(update(User).where(User.email == "ana@demo.pe").values(password_hash=hash_password("Otra#Clave2026", 4)))
        db.commit()
    assert other.get("/customer").status_code == 401


def test_technician_is_not_customer(env):
    accounts, other, _ = env
    other.cookies.set("techfix_session", login(accounts, "tecnico@taller.com"))
    res = other.get("/customer")
    assert res.status_code == 403 and res.json()["code"] == "customer_only"
    assert other.get("/user").json() == {"role": "TECHNICIAN"}


def test_from_env_requires_auth_secret(monkeypatch):
    monkeypatch.delenv("AUTH_SECRET", raising=False)
    monkeypatch.setattr("app.accounts.session.load_dotenv", lambda: None)
    with pytest.raises(RuntimeError, match="AUTH_SECRET"):
        SessionGuard.from_env()
