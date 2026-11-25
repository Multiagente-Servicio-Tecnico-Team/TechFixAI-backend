"""Infrastructure construction with mocks: no driver installation, SQL or sockets."""
from unittest.mock import Mock

import pytest
from app.database import decentralized_checkpoint as checkpoint

DSN = "postgresql://technical:private-password@localhost/technical_db"


def test_environment_independent_from_business_dsn(monkeypatch):
    for key in list(__import__("os").environ):
        if key.startswith("DECENTRALIZED_CHECKPOINT_"):
            monkeypatch.delenv(key)
    monkeypatch.setenv("DATABASE_URL", DSN)
    settings = checkpoint.load_checkpoint_settings()
    assert settings.dsn is None and settings.max_size == 5
    with pytest.raises(ValueError, match="DECENTRALIZED_CHECKPOINT_DSN"):
        checkpoint.build_checkpoint_resources(settings)
    monkeypatch.setenv("DECENTRALIZED_CHECKPOINT_DSN", DSN)
    monkeypatch.setenv("DECENTRALIZED_CHECKPOINT_POOL_MIN", "0")
    monkeypatch.setenv("DECENTRALIZED_CHECKPOINT_POOL_MAX", "4")
    monkeypatch.setenv("DECENTRALIZED_CHECKPOINT_POOL_TIMEOUT", "7.5")
    monkeypatch.setenv("DECENTRALIZED_CHECKPOINT_CONNECT_TIMEOUT", "8")
    settings = checkpoint.load_checkpoint_settings()
    assert (settings.dsn, settings.min_size, settings.max_size, settings.timeout, settings.connect_timeout) == (DSN, 0, 4, 7.5, 8)
    assert "private-password" not in repr(settings) and DSN not in repr(settings)


@pytest.mark.parametrize("changes", [
    {"dsn": "postgresql+pg8000://user:secret@host/db"}, {"dsn": "sqlite:///test.db"},
    {"dsn": "postgresql://user:secret@/"}, {"schema": "public"},
    {"schema": "pg_catalog"}, {"schema": "schema; DROP TABLE x"},
    {"min_size": True}, {"min_size": -1}, {"min_size": 6, "max_size": 5},
    {"max_size": 0}, {"max_size": "5"}, {"timeout": 0},
    {"timeout": float("nan")}, {"timeout": float("inf")},
    {"timeout": True}, {"connect_timeout": True}, {"connect_timeout": -1},
])
def test_invalid_settings(changes):
    with pytest.raises(ValueError) as error:
        checkpoint.CheckpointSettings(**{**{"dsn": DSN}, **changes})
    assert DSN not in str(error.value) and "secret" not in str(error.value)


def test_invalid_environment_number_does_not_echo_value(monkeypatch):
    monkeypatch.setenv("DECENTRALIZED_CHECKPOINT_POOL_MAX", "private-password")
    with pytest.raises(ValueError) as error:
        checkpoint.load_checkpoint_settings()
    assert "private-password" not in str(error.value)


@pytest.fixture
def factories(monkeypatch):
    pool, saver, row = Mock(), Mock(), object()
    pool_type, saver_type = Mock(return_value=pool), Mock(return_value=saver)
    monkeypatch.setattr(checkpoint, "_dependencies", lambda: (pool_type, saver_type, row))
    return pool, saver, row, pool_type, saver_type


def test_constructs_without_connecting_or_setup(factories):
    pool, saver, row, pool_type, saver_type = factories
    with checkpoint.build_checkpoint_resources(checkpoint.CheckpointSettings(dsn=DSN)) as resources:
        assert resources.pool is pool and resources.saver is saver
        pool_type.assert_called_once_with(conninfo=DSN, min_size=1, max_size=5, timeout=30.0, open=False,
                                         kwargs={"autocommit": True, "row_factory": row, "connect_timeout": 10,
                                                 "options": "-csearch_path=langgraph_decentralized"})
        saver_type.assert_called_once_with(pool)
        pool.open.assert_not_called()
        pool.connection.assert_not_called()
        saver.setup.assert_not_called()
    resources.close()
    pool.close.assert_called_once()
    with pytest.raises(RuntimeError):
        resources.__enter__()


def test_saver_constructor_failure_closes_pool_without_leaking(factories):
    pool, _, _, _, saver_type = factories
    saver_type.side_effect = RuntimeError(DSN)
    with pytest.raises(RuntimeError) as error:
        checkpoint.build_checkpoint_resources(checkpoint.CheckpointSettings(dsn=DSN))
    pool.close.assert_called_once()
    assert DSN not in str(error.value) and error.value.__suppress_context__


def test_pool_constructor_failure(factories):
    pool, _, _, pool_type, _ = factories
    pool_type.side_effect = RuntimeError(DSN)
    with pytest.raises(RuntimeError) as error:
        checkpoint.build_checkpoint_resources(checkpoint.CheckpointSettings(dsn=DSN))
    pool.close.assert_not_called()
    assert "private-password" not in str(error.value)


def test_closes_on_body_exception(factories):
    pool, _, _, _, _ = factories
    with pytest.raises(ValueError, match="caller failure"):
        with checkpoint.build_checkpoint_resources(checkpoint.CheckpointSettings(dsn=DSN)):
            raise ValueError("caller failure")
    pool.close.assert_called_once()


def test_close_failure_is_safe_and_can_be_retried(factories):
    pool, _, _, _, _ = factories
    resources = checkpoint.build_checkpoint_resources(checkpoint.CheckpointSettings(dsn=DSN))
    pool.close.side_effect = RuntimeError(DSN)
    with pytest.raises(RuntimeError) as error:
        resources.close()
    assert "private-password" not in str(error.value)
    pool.close.side_effect = None
    resources.close()
    assert pool.close.call_count == 2


def test_missing_dependency_reports_optional_requirements(monkeypatch):
    import sys
    monkeypatch.setitem(sys.modules, "psycopg", None)
    monkeypatch.setitem(sys.modules, "psycopg.rows", None)
    with pytest.raises(RuntimeError, match="requirements-checkpoint.txt"):
        checkpoint._dependencies()
