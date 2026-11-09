"""Real FastAPI lifespan, mocked storage and graphs; no database or LLM."""
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from app.accounts.config import Settings
from app.accounts.session import SessionCustomer
import app.main as main


class Guard:
    settings = Settings(database_url=None, auth_secret="s" * 48, secure_cookie=False)

    def require_customer(self, request):
        return SimpleNamespace(id=1)


def resources():
    pool = MagicMock()
    pool.max_size = 5
    return SimpleNamespace(pool=pool, saver=MagicMock(), close=MagicMock())


@pytest.fixture(autouse=True)
def ownership_mock(monkeypatch):
    repository = MagicMock()
    repository.register.side_effect = lambda **kw: {"thread_id": kw["thread_id"]}
    monkeypatch.setattr(main, "ConversationOwnersRepository", lambda pool: repository)
    monkeypatch.setattr(main, "ConversationLocks", lambda pool: SimpleNamespace(hold=lambda thread: nullcontext()))


def test_lifespan_reuses_saver_and_closes(monkeypatch):
    storage = resources()
    graph = MagicMock()
    graph.get_state.return_value = SimpleNamespace(values={}, next=())
    graph.invoke.return_value = {"messages": [AIMessage(content="Respuesta")], "customer_id": 1}
    build = MagicMock(return_value=graph)
    monkeypatch.setattr(main, "_build_decentralized_graph", build)
    factory = MagicMock(return_value=storage)
    app = main.create_app(session_guard=Guard(), checkpoint_resources_factory=factory,
                          trace_context_factory=nullcontext)
    with TestClient(app) as client:
        for _ in range(2):
            assert client.post("/api/chat", json={"pattern": "decentralized", "message": "Hola"}).status_code == 200
        build.assert_called_once_with(storage.saver)
        factory.assert_called_once()
        storage.pool.open.assert_called_once_with(wait=True)
        storage.saver.setup.assert_not_called()
        storage.close.assert_not_called()
    storage.close.assert_called_once()
    assert app.state.decentralized_graph is None
    assert app.state.checkpoint_resources is None


@pytest.mark.parametrize("failure", ["factory", "open", "graph"])
def test_failure_no_fallback_other_pattern_survives(monkeypatch, failure):
    storage = resources()
    factory = MagicMock(return_value=storage)
    build = MagicMock(return_value=MagicMock())
    if failure == "factory":
        factory.side_effect = RuntimeError("private details")
    elif failure == "open":
        storage.pool.open.side_effect = RuntimeError("private details")
    else:
        build.side_effect = RuntimeError("private details")
    monkeypatch.setattr(main, "_build_decentralized_graph", build)
    other = MagicMock()
    other.invoke.return_value = {"messages": [AIMessage(content="Respuesta")], "outcome": "done"}
    monkeypatch.setattr(main, "_build_hierarchical_graph", lambda: other)
    app = main.create_app(session_guard=Guard(), checkpoint_resources_factory=factory,
                          trace_context_factory=nullcontext)
    with TestClient(app) as client:
        response = client.post("/api/chat", json={"pattern": "decentralized", "message": "Hola"})
        assert response.status_code == 503
        assert "private details" not in response.text
        assert client.post("/api/chat", json={"pattern": "hierarchical", "message": "Hola"}).status_code == 200
    assert storage.close.call_count == (0 if failure == "factory" else 1)


def test_runtime_database_failure_returns_503(monkeypatch):
    from psycopg import OperationalError
    storage = resources()
    graph = MagicMock()
    graph.get_state.return_value = SimpleNamespace(values={}, next=())
    graph.invoke.side_effect = OperationalError("private details")
    monkeypatch.setattr(main, "_build_decentralized_graph", lambda saver: graph)
    app = main.create_app(session_guard=Guard(), checkpoint_resources_factory=lambda: storage,
                          trace_context_factory=nullcontext)
    with TestClient(app) as client:
        response = client.post("/api/chat", json={"pattern": "decentralized", "message": "Hola"})
        assert response.status_code == 503 and "private details" not in response.text
    storage.close.assert_called_once()


def test_injected_graphs_do_not_open_storage():
    factory = MagicMock(side_effect=AssertionError("No storage"))
    app = main.create_app(session_guard=Guard(), graph_factories={name: MagicMock() for name in main.PATTERN_NAMES},
                          checkpoint_resources_factory=factory)
    with TestClient(app):
        factory.assert_not_called()


@pytest.mark.parametrize("stage", ["configuration", "pool_construction", "pool_open", "graph_construction", "resource_association"])
def test_safe_initialization_stage_diagnostics(monkeypatch, caplog, stage):
    import app.database.decentralized_checkpoint as checkpoint
    storage = resources()
    secret_message = "private DSN password must not appear"
    failure = RuntimeError(secret_message)
    monkeypatch.setattr(checkpoint, "load_checkpoint_settings", lambda: object())
    monkeypatch.setattr(main, "_checkpoint_resources", lambda settings: storage)
    monkeypatch.setattr(main, "_build_decentralized_graph", lambda saver: MagicMock())
    if stage == "configuration":
        monkeypatch.setattr(checkpoint, "load_checkpoint_settings", MagicMock(side_effect=failure))
    elif stage == "pool_construction":
        monkeypatch.setattr(main, "_checkpoint_resources", MagicMock(side_effect=failure))
    elif stage == "pool_open":
        storage.pool.open.side_effect = failure
    elif stage == "graph_construction":
        monkeypatch.setattr(main, "_build_decentralized_graph", MagicMock(side_effect=failure))
    else:
        monkeypatch.setattr(main, "ConversationOwnersRepository", MagicMock(side_effect=failure))
    app = main.create_app(session_guard=Guard(), trace_context_factory=nullcontext)
    with TestClient(app) as client:
        assert client.get("/openapi.json").status_code == 200
        assert client.post("/api/chat", json={"pattern": "decentralized", "message": "Hola"}).status_code == 503
    assert f"stage={stage}; type=RuntimeError" in caplog.text
    assert secret_message not in caplog.text
    assert storage.close.call_count == (0 if stage in {"configuration", "pool_construction"} else 1)


@pytest.mark.parametrize("existing", [False, True])
def test_explicit_project_env_loaded_before_accounts_and_storage(monkeypatch, tmp_path, caplog, existing):
    import os
    import app.database.decentralized_checkpoint as checkpoint
    from app.accounts.config import Settings as AccountSettings
    secret = "synthetic-secret-for-isolated-test-" * 2
    external = "external-secret-for-isolated-test-" * 2
    (tmp_path / ".env").write_text(
        f"AUTH_SECRET={secret}\nDECENTRALIZED_CHECKPOINT_DSN=postgresql://localhost/isolated_test\nLANGSMITH_PROJECT=taller-red-descentralizada\n",
        encoding="utf-8")
    monkeypatch.setattr(main, "PROJECT_ROOT", tmp_path)
    for key in ("AUTH_SECRET", "DECENTRALIZED_CHECKPOINT_DSN", "LANGSMITH_PROJECT"):
        monkeypatch.delenv(key, raising=False)
    if existing:
        monkeypatch.setenv("AUTH_SECRET", external)
    expected = external if existing else secret
    original = AccountSettings.from_env
    def account_settings():
        result = original()
        assert result.auth_secret == expected
        return result
    monkeypatch.setattr(main.AccountSettings, "from_env", account_settings)
    storage = resources()
    def load_settings():
        assert os.environ["AUTH_SECRET"] == expected
        assert os.environ["LANGSMITH_PROJECT"] == "taller-red-descentralizada"
        return checkpoint.CheckpointSettings(dsn=os.environ["DECENTRALIZED_CHECKPOINT_DSN"])
    monkeypatch.setattr(checkpoint, "load_checkpoint_settings", load_settings)
    monkeypatch.setattr(main, "_checkpoint_resources", lambda settings: storage)
    monkeypatch.setattr(main, "_build_decentralized_graph", lambda saver: MagicMock())
    app = main.create_app(trace_context_factory=nullcontext)
    with TestClient(app):
        assert original().auth_secret == expected
    assert "se usa un secreto temporal" not in caplog.text
