from contextlib import nullcontext
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, HumanMessage
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.accounts.api import create_app as create_accounts_app
from app.accounts.config import Settings as AccountSettings
from app.accounts.models import Base
from app.accounts.session import SessionGuard
from app.chat.contract import QuoteOut
from app.adapters.patterns.hierarchical import HierarchicalPattern
from app.main import PATTERN_NAMES, create_app
from app.settings import Settings


PASSWORD = "PatternTest#2026"
ACCOUNT_SETTINGS = AccountSettings(
    database_url=None,
    auth_secret="s" * 48,
    secure_cookie=False,
    bcrypt_rounds=4,
)


def test_hierarchical_warranty_claim_returns_ticket_for_portal():
    ticket = HierarchicalPattern.ticket(
        {
            "outcome": "warranty_claim_registered",
            "ticket_code": "TCK-ABC123",
            "ticket_status": "WARRANTY_IN_REVIEW",
        },
    )

    assert ticket is not None
    assert ticket.code == "TCK-ABC123"
    assert ticket.status == "WARRANTY_IN_REVIEW"


class FakeGraph:
    def __init__(self, pattern):
        self.pattern = pattern
        self.calls = []
        self.checkpoint_values = {}

    def get_state(self, config):
        return SimpleNamespace(values=self.checkpoint_values)

    def invoke(self, state, *, config):
        self.calls.append((state, config))
        message = state["messages"][-1].content
        if self.pattern == "decentralized":
            return {"messages": [AIMessage(content=f"Red: {message}")]}
        if self.pattern == "hierarchical":
            confirmed = message.casefold().startswith("sí")
            return {
                "messages": [AIMessage(content="Propuesta" if not confirmed else "Guardado")],
                "outcome": "quoted" if confirmed else "awaiting_confirmation",
                "ticket_code": "ST-ABC123",
                "quote": {
                    "labor_task_type": "diagnosis",
                    "labor_cost": Decimal("50.00"),
                    "parts_cost": Decimal("0.00"),
                    "total_amount": Decimal("50.00"),
                    "parts": [],
                },
            }
        confirmed = message.casefold().startswith("sí")
        return {
            "response": "Propuesta" if not confirmed else "Guardado",
            "awaiting_ticket_confirmation": not confirmed,
            "quote_id": 2 if confirmed else None,
            "ticket_code": "TCK-ABC123" if confirmed else None,
            "labor_task_type": "diagnosis",
            "labor_cost": Decimal("50.00"),
            "available_parts": [],
            "total": Decimal("50.00"),
        }


@pytest.fixture
def pattern_client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    accounts = TestClient(create_accounts_app(ACCOUNT_SETTINGS, factory))
    accounts.post(
        "/registro",
        json={
            "nombre": "Ana Torres",
            "email": "ana@demo.pe",
            "telefono": "+51987654321",
            "password": PASSWORD,
        },
    )
    accounts.post("/login", json={"email": "ana@demo.pe", "password": PASSWORD})

    graphs = {pattern: FakeGraph(pattern) for pattern in PATTERN_NAMES}
    settings = Settings(
        groq_api_key=None,
        groq_model=None,
        database_url=None,
        langsmith_api_key=None,
        langsmith_tracing=False,
        langsmith_project="tests",
        langsmith_hide_inputs=True,
        langsmith_hide_outputs=True,
        labor_maintenance_price=Decimal("40.00"),
        labor_diagnosis_price=Decimal("50.00"),
    )
    app = create_app(
        session_guard=SessionGuard(ACCOUNT_SETTINGS, factory),
        graph_factories={
            name: (lambda graph=graph: graph)
            for name, graph in graphs.items()
        },
        settings_factory=lambda: settings,
        trace_context_factory=nullcontext,
    )
    client = TestClient(app)
    client.cookies.set("techfix_session", accounts.cookies.get("techfix_session"))
    yield client, graphs
    engine.dispose()


def test_patterns_require_authenticated_customer(pattern_client):
    client, _ = pattern_client
    client.cookies.clear()

    assert client.get("/api/chat/patterns").status_code == 401
    assert client.post("/api/chat", json={"message": "hola"}).status_code == 401


def test_selector_lists_patterns_and_chat_runs_selected_graph(pattern_client):
    client, graphs = pattern_client

    patterns = client.get("/api/chat/patterns")
    assert patterns.status_code == 200
    assert [item["id"] for item in patterns.json()["patterns"]] == list(PATTERN_NAMES)

    response = client.post(
        "/api/chat",
        json={"message": "Mi laptop no enciende", "pattern": "decentralized"},
    )
    assert response.status_code == 200
    assert response.json()["pattern"] == "decentralized"
    assert response.json()["reply"] == "Red: Mi laptop no enciende"
    assert graphs["decentralized"].calls[0][1]["tags"] == [
        "service-chat",
        "pattern:decentralized",
    ]
    metadata = graphs["decentralized"].calls[0][1]["metadata"]
    assert metadata["pattern"] == "decentralized"
    assert metadata["conversation_id"] == response.json()["conversation_id"]
    assert "customer_id" not in metadata
    assert not graphs["hierarchical"].calls
    assert not graphs["orchestrator"].calls


def test_decentralized_api_resets_turn_controls_from_checkpoint(pattern_client):
    client, graphs = pattern_client
    first = client.post(
        "/api/chat",
        json={"message": "Consulta inicial", "pattern": "decentralized"},
    )
    conversation_id = first.json()["conversation_id"]
    graph = graphs["decentralized"]
    graph.checkpoint_values = {
        "messages": [HumanMessage(content="anterior"), AIMessage(content="respuesta")],
        "handoff_count": 5,
        "handoff_history": [{"origen": "soporte", "destino": "tecnico"}],
        "tool_iterations": {"soporte": 4},
        "errors": ["fallo previo"],
        "current_agent": "tecnico",
    }

    response = client.post(
        "/api/chat",
        json={
            "conversation_id": conversation_id,
            "message": "Nueva pregunta",
            "pattern": "decentralized",
        },
    )

    assert response.status_code == 200
    state = graph.calls[-1][0]
    assert state["turn_start_index"] == 2
    assert state["handoff_count"] == 0
    assert state["handoff_history"] == []
    assert state["tool_iterations"] == {}
    assert state["errors"] == []
    assert state["next_agent"] is None
    assert state["messages"] == [HumanMessage(content="Nueva pregunta")]


def test_hierarchical_quote_save_and_pattern_lock(pattern_client):
    client, graphs = pattern_client
    response = client.post(
        "/api/chat",
        json={"message": "No se conoce la falla", "pattern": "hierarchical"},
    )
    data = response.json()

    assert response.status_code == 200
    assert data["quote"] == {
        "status": "proposed",
        "lines": [{"label": "Diagnóstico técnico", "amount": "50.00"}],
        "total": "50.00",
        "currency": "PEN",
    }
    assert "ticket" not in data

    accepted = client.post(
        "/api/chat",
        json={
            "conversation_id": data["conversation_id"],
            "action": "accept_quote",
            "pattern": "hierarchical",
        },
    )
    assert accepted.status_code == 200
    assert accepted.json()["quote"]["status"] == "saved"
    assert accepted.json()["ticket"]["code"] == "ST-ABC123"
    assert accepted.json()["ticket"]["status"] == "QUOTED"
    assert isinstance(graphs["hierarchical"].calls[-1][0]["messages"][-1], HumanMessage)
    assert graphs["hierarchical"].calls[0][0]["customer_id"] == 1

    conflict = client.post(
        "/api/chat",
        json={
            "conversation_id": data["conversation_id"],
            "message": "Siguiente mensaje",
            "pattern": "orchestrator",
        },
    )
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "pattern_locked"


def test_orchestrator_quote_preview_maps_to_frontend_contract(pattern_client):
    client, graphs = pattern_client
    response = client.post(
        "/api/chat",
        json={"message": "Necesito revisión", "pattern": "orchestrator"},
    )

    assert response.status_code == 200
    assert response.json()["quote"] == QuoteOut(
        status="proposed",
        lines=[{"label": "Diagnóstico técnico", "amount": "50.00"}],
        total="50.00",
    ).model_dump()
    assert graphs["orchestrator"].calls[0][0]["user_id"] == 1
