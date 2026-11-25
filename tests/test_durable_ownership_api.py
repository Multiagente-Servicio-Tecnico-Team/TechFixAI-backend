from contextlib import nullcontext
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from test_checkpoint_api_lifespan import Guard
from app.main import create_app, PATTERN_NAMES
from app.database.conversation_owners import ConversationNotFound, ConversationConflict, ConversationStorageError


def client_for(repo, graph, locks=None):
    return TestClient(create_app(session_guard=Guard(),
        graph_factories={name: lambda: graph for name in PATTERN_NAMES},
        conversation_owners_repository=repo, trace_context_factory=nullcontext,
        conversation_locks=locks or type("TestLocks", (), {"hold": lambda self, thread: nullcontext()})()))


def test_registration_then_recovery_in_new_app_uses_durable_thread():
    repo, graph = MagicMock(), MagicMock()
    graph.invoke.return_value = {"messages": [AIMessage(content="Respuesta")]}
    repo.register.side_effect = lambda **kw: {"thread_id": kw["thread_id"]}
    with client_for(repo, graph) as client:
        response = client.post("/api/chat", json={"pattern": "decentralized", "message": "Hola"})
        assert response.status_code == 200
        cid = response.json()["conversation_id"]
    assert repo.register.call_args.kwargs["authenticated_customer_id"] == 1
    repo.authorize.return_value = {"thread_id": "stored-thread"}
    with client_for(repo, graph) as client:
        response = client.post("/api/chat", json={"pattern": "decentralized", "message": "Continuar", "conversation_id": cid})
        assert response.status_code == 200
        assert graph.invoke.call_args.kwargs["config"]["configurable"]["thread_id"] == "stored-thread"
        response = client.post("/api/chat", json={"pattern": "hierarchical", "message": "Continuar", "conversation_id": cid})
        assert response.status_code == 409


@pytest.mark.parametrize("error,status", [(ConversationNotFound(),404), (ConversationConflict(),409), (ConversationStorageError(),503)])
def test_authorization_rejection_never_calls_graph(error, status):
    repo, graph = MagicMock(), MagicMock()
    repo.authorize.side_effect = error
    with client_for(repo, graph) as client:
        response = client.post("/api/chat", json={"pattern": "decentralized", "message": "Hola", "conversation_id": "existing"})
        assert response.status_code == status
    graph.invoke.assert_not_called()


def test_registration_failure_no_graph_execution():
    repo, graph = MagicMock(), MagicMock()
    repo.register.side_effect = ConversationStorageError()
    with client_for(repo, graph) as client:
        assert client.post("/api/chat", json={"pattern": "decentralized", "message": "Hola"}).status_code == 503
    graph.invoke.assert_not_called()


@pytest.mark.parametrize("kind,status", [("busy",409), ("storage",503)])
def test_coordination_rejection_does_not_invoke_graph(kind, status):
    from app.database.conversation_locks import ConversationBusy, ConversationLockStorageError
    repo, graph, locks = MagicMock(), MagicMock(), MagicMock()
    repo.authorize.return_value = {"thread_id": "stored-thread"}
    error = ConversationBusy() if kind == "busy" else ConversationLockStorageError()
    locks.hold.return_value.__enter__.side_effect = error
    with client_for(repo, graph, locks) as client:
        response = client.post("/api/chat", json={"pattern": "decentralized", "message": "Hola", "conversation_id": "existing"})
        assert response.status_code == status
    graph.invoke.assert_not_called()
    locks.hold.assert_called_once_with("stored-thread")
