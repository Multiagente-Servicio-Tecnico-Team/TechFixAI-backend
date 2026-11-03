"""Current API composition with the original network protocol; mocked PostgreSQL."""
from contextlib import contextmanager, nullcontext
from types import SimpleNamespace
from unittest.mock import MagicMock
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from app.infrastructure.chat_app import build_chat_app
from app.adapters.patterns.registry import PATTERN_NAMES
from app.database.conversation_owners import ConversationNotFound
from app.accounts.config import Settings as AccountSettings


class Guard:
    settings = AccountSettings(database_url=None, auth_secret="s" * 48, secure_cookie=False)
    def require_customer(self, request): return SimpleNamespace(id=1)


def test_original_public_id_is_preserved_and_owner_precedes_the_distributed_lock():
    events, owners = [], MagicMock()
    owners.authorize.side_effect = lambda **kw: (events.append("authorize") or {"thread_id": "private-thread"})
    @contextmanager
    def lock(thread):
        assert thread == "private-thread"
        events.append("lock")
        yield
    graph = MagicMock()
    graph.invoke.return_value = {"messages": [AIMessage(content="Respuesta")], "customer_id": 1}
    app = build_chat_app(session_guard=Guard(), graph_factories={key: lambda: graph for key in PATTERN_NAMES}, conversation_owners_repository=owners, conversation_locks=SimpleNamespace(hold=lock), trace_context_factory=nullcontext)
    with TestClient(app) as client:
        response = client.post("/api/chat", json={"pattern": "decentralized", "conversation_id": "public-conversation", "message": "Hola", "customer_id": 99})
        assert response.status_code == 200
        assert response.json()["conversation_id"] == "public-conversation"
        assert events == ["authorize", "lock"]
        args = graph.invoke.call_args
        assert args.args[0]["customer_id"] == 1
        assert args.kwargs["config"]["configurable"] == {"thread_id": "private-thread", "conversation_id": "public-conversation"}
        graph.reset_mock()
        owners.authorize.side_effect = ConversationNotFound()
        assert client.post("/api/chat", json={"pattern": "decentralized", "conversation_id": "public-conversation", "message": "Hola"}).status_code == 404
        graph.invoke.assert_not_called()


def test_lifespan_closes_resources_and_does_not_reuse_graph_from_closed_pool(monkeypatch):
    import app.infrastructure.decentralized_runtime as runtime
    storages = [SimpleNamespace(pool=MagicMock(), saver=MagicMock(), close=MagicMock()) for _ in range(2)]
    graphs = [MagicMock(), MagicMock()]
    for resource, graph in zip(storages, graphs):
        resource.pool.max_size = 4
        graph.get_state.return_value = SimpleNamespace(values={}, next=())
        graph.invoke.return_value = {"messages": [AIMessage(content="Respuesta")], "customer_id": 1}
    owners = MagicMock()
    owners.register.side_effect = lambda **kw: {"thread_id": kw["thread_id"]}
    monkeypatch.setattr(runtime, "ConversationOwnersRepository", lambda pool: owners)
    monkeypatch.setattr(runtime, "ConversationLocks", lambda pool: SimpleNamespace(hold=lambda thread: nullcontext()))
    monkeypatch.setattr(runtime, "_build_decentralized_graph", MagicMock(side_effect=graphs))
    app = build_chat_app(session_guard=Guard(), checkpoint_resources_factory=MagicMock(side_effect=storages), trace_context_factory=nullcontext)
    for index in range(2):
        with TestClient(app) as client:
            assert client.post("/api/chat", json={"pattern": "decentralized", "message": "Hola"}).status_code == 200
            storages[index].saver.setup.assert_not_called()
            assert graphs[index].invoke.call_count == 1
        storages[index].close.assert_called_once()
        assert app.state.patterns["decentralized"]._graph is None
        assert app.state.checkpoint_resources is None


def test_storage_failure_never_falls_back_to_memory(monkeypatch):
    import app.infrastructure.decentralized_runtime as runtime
    factory = MagicMock(side_effect=RuntimeError("synthetic failure"))
    app = build_chat_app(session_guard=Guard(), checkpoint_resources_factory=factory, trace_context_factory=nullcontext)
    with TestClient(app) as client:
        assert client.post("/api/chat", json={"pattern": "decentralized", "message": "Hola"}).status_code == 503
        assert client.get("/openapi.json").status_code == 200
    assert app.state.decentralized_graph is None
