from contextlib import nullcontext
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.accounts.api import create_app as create_accounts_app
from app.accounts.config import Settings as AccountSettings
from app.accounts.models import Base
from app.accounts.session import SessionGuard
from app.main import PATTERN_NAMES, create_app
from app.settings import Settings


PASSWORD = "PatternPortal#2026"
ACCOUNT_SETTINGS = AccountSettings(
    database_url=None,
    auth_secret="p" * 48,
    secure_cookie=False,
    bcrypt_rounds=4,
)


class EchoGraph:
    def invoke(self, state, *, config):
        return {"messages": [AIMessage(content="Respuesta de prueba")]}


@pytest.fixture
def portal():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    accounts = TestClient(create_accounts_app(ACCOUNT_SETTINGS, factory))
    for name, email in (("Ana Torres", "ana@demo.pe"), ("Luis Pérez", "luis@demo.pe")):
        accounts.post(
            "/registro",
            json={
                "nombre": name,
                "email": email,
                "telefono": "+51987654321",
                "password": PASSWORD,
            },
        )

    graphs = {pattern: EchoGraph() for pattern in PATTERN_NAMES}
    settings = Settings(
        groq_api_key=None,
        groq_model=None,
        database_url=None,
        langsmith_api_key=None,
        langsmith_tracing=False,
        langsmith_project="portal-tests",
        langsmith_hide_inputs=True,
        langsmith_hide_outputs=True,
        labor_maintenance_price=Decimal("40.00"),
        labor_diagnosis_price=Decimal("50.00"),
    )
    app = create_app(
        session_guard=SessionGuard(ACCOUNT_SETTINGS, factory),
        graph_factories={key: (lambda graph=graph: graph) for key, graph in graphs.items()},
        settings_factory=lambda: settings,
        trace_context_factory=nullcontext,
    )
    yield accounts, TestClient(app)
    engine.dispose()


def log_in(accounts, client, email):
    accounts.cookies.clear()
    response = accounts.post("/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200
    client.cookies.set("techfix_session", accounts.cookies.get("techfix_session"))
    return client


def test_chat_and_pattern_catalog_require_a_customer_session(portal):
    _, client = portal

    assert client.get("/api/chat/patterns").status_code == 401
    assert client.post("/api/chat", json={"message": "hola"}).status_code == 401


def test_conversation_is_private_to_the_authenticated_customer(portal):
    accounts, client = portal
    log_in(accounts, client, "ana@demo.pe")
    response = client.post("/api/chat", json={"message": "Consulta privada"})
    assert response.status_code == 200

    log_in(accounts, client, "luis@demo.pe")
    other_customer = client.post(
        "/api/chat",
        json={
            "conversation_id": response.json()["conversation_id"],
            "message": "No debo ver esto",
        },
    )
    assert other_customer.status_code == 404


def test_invalid_chat_body_is_rejected_without_echoing_long_input(portal):
    accounts, client = portal
    log_in(accounts, client, "ana@demo.pe")
    response = client.post("/api/chat", json={"message": "x" * 2001})

    assert response.status_code == 422
    assert "x" * 50 not in response.text
