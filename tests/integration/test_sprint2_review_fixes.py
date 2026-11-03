"""Regresiones de compatibilidad, composicion e independencia del almacenamiento."""
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from app.accounts.config import Settings
from app.adapters.patterns.registry import PATTERN_NAMES
from app.database.conversation_owners import ConversationNotFound, ConversationStorageError
from app.infrastructure.chat_app import build_chat_app


class Guard:
    settings = Settings(database_url=None, auth_secret="s" * 48, secure_cookie=False)

    def require_customer(self, request):
        return SimpleNamespace(id=2 if request.headers.get("x-other") else 1)


def factories(graph):
    return {name: lambda: graph for name in PATTERN_NAMES}


def test_procurement_compatibility_reuses_the_common_unavailable_node():
    from app.agents.procurement import procurement_node as common
    from app.agents.decentralized.compras import procurement_node, compras_node
    from app.agents.decentralized.purchasing import purchasing_node
    assert procurement_node is common
    assert compras_node is purchasing_node
    assert procurement_node is not purchasing_node


def test_normal_composition_does_not_silently_drop_auth_routes(monkeypatch):
    import app.main as main
    calls = []
    def accounts(**kwargs):
        calls.append(kwargs)
        app = FastAPI()
        app.state.session_factory = kwargs["session_factory"]
        return app
    monkeypatch.setattr(main, "create_accounts_app", accounts)
    factory = object()
    app = main.create_app(session_guard=Guard(), session_factory=factory, chat_app=FastAPI())
    assert any(route.path == "/auth" for route in app.routes)
    assert calls[0]["session_factory"] is factory
    with pytest.raises(ValueError, match="session_factory"):
        main.create_app(session_guard=Guard(), chat_app=FastAPI())


def test_auth_route_omission_is_explicit_and_requires_injected_dependencies(monkeypatch):
    import app.main as main
    accounts = MagicMock(side_effect=AssertionError("No accounts engine in explicit test mode"))
    monkeypatch.setattr(main, "create_accounts_app", accounts)
    with pytest.raises(ValueError):
        main.create_app(test_without_auth_routes=True, chat_app=FastAPI())
    with pytest.raises(ValueError):
        main.create_app(test_without_auth_routes=True, session_guard=Guard(), chat_app=FastAPI())
    app = main.create_app(test_without_auth_routes=True, session_guard=Guard(),
                          graph_factories=factories(MagicMock()), chat_app=FastAPI())
    assert not any(route.path == "/auth" for route in app.routes)
    accounts.assert_not_called()


@pytest.mark.parametrize("pattern", ["hierarchical", "orchestrator"])
def test_other_patterns_do_not_query_durable_ownership_for_unknown_or_local_ids(pattern):
    owners = MagicMock()
    owners.authorize.side_effect = ConversationStorageError()
    graph = MagicMock()
    graph.invoke.return_value = {"messages": [AIMessage(content="Respuesta")], "customer_id": 1}
    app = build_chat_app(session_guard=Guard(), graph_factories=factories(graph),
        conversation_owners_repository=owners, conversation_locks=MagicMock(), trace_context_factory=nullcontext)
    with TestClient(app) as client:
        body = {"pattern": pattern, "message": "Hola"}
        unknown = client.post("/api/chat", json={**body, "conversation_id": "unknown"})
        assert unknown.status_code == 404
        graph.invoke.assert_not_called()
        first = client.post("/api/chat", json=body)
        assert first.status_code == 200
        cid = first.json()["conversation_id"]
        assert client.post("/api/chat", json={**body, "conversation_id": cid}).status_code == 200
        owners.authorize.assert_not_called()
        owners.register.assert_not_called()


def test_decentralized_owner_is_always_authorized_and_switches_are_local():
    owners = MagicMock()
    owners.authorize.return_value = {"thread_id": "private-thread"}
    graph = MagicMock()
    graph.invoke.return_value = {"messages": [AIMessage(content="Respuesta")], "customer_id": 1}
    locks = SimpleNamespace(hold=lambda thread: nullcontext())
    app = build_chat_app(session_guard=Guard(), graph_factories=factories(graph),
        conversation_owners_repository=owners, conversation_locks=locks, trace_context_factory=nullcontext)
    with TestClient(app) as client:
        body = {"pattern": "decentralized", "message": "Hola", "conversation_id": "durable-existing"}
        assert client.post("/api/chat", json=body).status_code == 200
        owners.authorize.assert_called_once()
        owners.authorize.reset_mock()
        for pattern in ("hierarchical", "orchestrator"):
            response = client.post("/api/chat", json={**body, "pattern": pattern})
            assert response.status_code == 409
            assert response.json()["code"] == "pattern_locked"
        owners.authorize.assert_not_called()
        graph.reset_mock()
        owners.authorize.side_effect = ConversationNotFound()
        assert client.post("/api/chat", json=body, headers={"x-other": "1"}).status_code == 404
        graph.invoke.assert_not_called()
        owners.authorize.side_effect = ConversationStorageError()
        assert client.post("/api/chat", json=body).status_code == 503
        graph.invoke.assert_not_called()
        assert owners.authorize.call_count == 2


def test_reference_fixtures_have_explicit_namespaces():
    from tests.integration import test_inventory_matching as inventory
    from tests.decentralized_reference import test_software_e2e as software
    assert inventory.__name__ == "tests.integration.test_inventory_matching"
    assert software.__name__ == "tests.decentralized_reference.test_software_e2e"
