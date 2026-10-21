"""Pruebas del punto de entrada unificado de cuentas y chat."""

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.accounts.config import Settings as AccountSettings
from app.accounts.models import Base
from app.combined import create_app


PASSWORD = "CombinedTest#2026"


def test_login_cookie_authenticates_chat_on_same_app():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    settings = AccountSettings(
        database_url=None,
        auth_secret="combined-test-secret-" * 3,
        secure_cookie=False,
        bcrypt_rounds=4,
    )

    with TestClient(create_app(settings=settings, session_factory=factory)) as client:
        assert client.get("/api/chat/patterns").status_code == 401

        registered = client.post(
            "/auth/registro",
            json={
                "nombre": "Ana Torres",
                "email": "ana@demo.pe",
                "telefono": "+51987654321",
                "password": PASSWORD,
            },
        )
        assert registered.status_code == 201

        logged_in = client.post(
            "/auth/login",
            json={"email": "ana@demo.pe", "password": PASSWORD},
        )
        assert logged_in.status_code == 200
        assert client.get("/auth/me").status_code == 200

        patterns = client.get("/api/chat/patterns")
        assert patterns.status_code == 200
        assert {pattern["id"] for pattern in patterns.json()["patterns"]} == {
            "hierarchical",
            "orchestrator",
            "decentralized",
        }

    engine.dispose()
