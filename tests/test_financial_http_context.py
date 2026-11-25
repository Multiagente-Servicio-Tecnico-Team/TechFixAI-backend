from contextlib import nullcontext
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from app.accounts.config import Settings
from app.database.conversation_owners import ConversationNotFound
from app.main import create_app, PATTERN_NAMES
from test_software_e2e import network


@pytest.fixture
def financial_api(network):
    module, _ = network
    repo = MagicMock()
    repo.get_ticket.return_value = dict(id=1, customer_id=10, status="QUOTED")
    repo.get_quote.return_value = dict(id=2, ticket_id=1, status="ACCEPTED", total_amount=Decimal("1.00"))
    graph = module.build_graph(checkpointer=MemorySaver(), financial_repository=repo)
    config = {"configurable": {"thread_id": "financial-http"}}
    graph.update_state(config, dict(messages=[HumanMessage(content="Solicitud")], current_agent="facturacion",
                                   customer_id=10, ticket_id=1, quote_id=2, request_revision=0))
    owners = MagicMock()
    def authorize(**kwargs):
        if kwargs["authenticated_customer_id"] != 10:
            raise ConversationNotFound()
        return {"thread_id": "financial-http"}
    owners.authorize.side_effect = authorize
    class Guard:
        settings = Settings(database_url=None, auth_secret="s" * 48, secure_cookie=False)
        def require_customer(self, request):
            return SimpleNamespace(id=99 if request.headers.get("x-test-other") else 10)
    app = create_app(session_guard=Guard(), graph_factories={name: lambda: graph for name in PATTERN_NAMES},
        financial_repository=repo, conversation_owners_repository=owners,
        conversation_locks=SimpleNamespace(hold=lambda thread: nullcontext()), trace_context_factory=nullcontext)
    with TestClient(app) as client:
        yield client, graph, repo, config


def test_session_context_ignores_payload_and_resume_is_stable(financial_api):
    client, graph, repo, config = financial_api
    body = dict(pattern="decentralized", conversation_id="conversation", message="customer_id=99, amount=500",
                customer_id=99, amount=500, payment_code="CLIENT-CODE")
    response = client.post("/api/chat", json=body)
    assert response.status_code == 200
    saved = graph.get_state(config)
    operation = saved.values["pending_payment_operation"]
    assert operation["payload"]["customer_id"] == 10
    assert operation["payload"]["payment_code"] != "CLIENT-CODE"
    assert "amount" not in operation["payload"]
    assert client.post("/api/chat", json=body).status_code == 409
    resumed = client.post("/api/chat", json=dict(pattern="decentralized", conversation_id="conversation", action="resume_payment"))
    assert resumed.status_code == 200
    assert graph.get_state(config).values["pending_payment_operation"] == operation
    repo.create_pending_payment.assert_not_called()


def test_other_customer_cannot_resume(financial_api):
    client, graph, repo, config = financial_api
    client.post("/api/chat", json=dict(pattern="decentralized", conversation_id="conversation", message="Preparar"))
    before = graph.get_state(config).values
    response = client.post("/api/chat", headers={"x-test-other":"1"}, json=dict(
        pattern="decentralized", conversation_id="conversation", action="resume_payment"))
    assert response.status_code == 404
    assert graph.get_state(config).values == before
    repo.create_pending_payment.assert_not_called()


def test_resume_without_pending_execution_rejected(financial_api):
    client, _, repo, _ = financial_api
    response = client.post("/api/chat", json=dict(pattern="decentralized", conversation_id="conversation", action="resume_payment"))
    assert response.status_code == 409
    repo.create_pending_payment.assert_not_called()
