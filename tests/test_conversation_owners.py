"""Injected pool and transactions only; no PostgreSQL connection."""
from unittest.mock import MagicMock

import pytest

from app.database.conversation_owners import (
    ConversationOwnersRepository, ConversationConflict,
    ConversationNotFound, ConversationStorageError,
)


def owner(**changes):
    return dict(conversation_id="conversation-a", thread_id="thread-a", customer_id=1,
                pattern="decentralized", created_at="before", updated_at="before", **changes)


@pytest.fixture
def storage():
    pool, conn, tx = MagicMock(), MagicMock(), MagicMock()
    pool.connection.return_value.__enter__.return_value = conn
    conn.transaction.return_value = tx
    return ConversationOwnersRepository(pool), conn, tx


def register(repo, **changes):
    return repo.register(**{**dict(conversation_id="conversation-a", thread_id="thread-a",
                                   authenticated_customer_id=1), **changes})


def test_register_and_exact_retry(storage):
    repo, conn, tx = storage
    conn.execute.return_value.fetchone.side_effect = [owner(), None, owner()]
    assert register(repo) == owner()
    assert register(repo) == owner()
    assert conn.execute.call_args_list[0].args[1] == ("conversation-a", "thread-a", 1, "decentralized")
    assert "ON CONFLICT DO NOTHING" in conn.execute.call_args_list[0].args[0]
    assert tx.__exit__.call_args.args == (None, None, None)


@pytest.mark.parametrize("existing", [None, {**owner(), "customer_id": 2},
                                     {**owner(), "thread_id": "other"}, {**owner(), "pattern": "other"}])
def test_registration_conflicts_roll_back(storage, existing):
    repo, conn, tx = storage
    conn.execute.return_value.fetchone.side_effect = [None, existing]
    with pytest.raises(ConversationConflict):
        register(repo)
    assert tx.__exit__.call_args.args[0] is ConversationConflict


def test_authorized_recovery_and_isolation(storage):
    repo, conn, _ = storage
    conn.execute.return_value.fetchone.side_effect = [owner(), None, {**owner(), "conversation_id": "b", "customer_id": 2}]
    assert repo.authorize(conversation_id="conversation-a", authenticated_customer_id=1) == owner()
    with pytest.raises(ConversationNotFound):
        repo.authorize(conversation_id="conversation-a", authenticated_customer_id=2)
    assert repo.authorize(conversation_id="b", authenticated_customer_id=2)["customer_id"] == 2
    assert conn.execute.call_args_list[1].args[1] == ("conversation-a", 2)


def test_touch_updates_only_activity(storage):
    repo, conn, _ = storage
    updated = {**owner(), "updated_at": "after"}
    conn.execute.return_value.fetchone.side_effect = [owner(), updated]
    assert repo.touch(conversation_id="conversation-a", authenticated_customer_id=1) == updated
    sql, params = conn.execute.call_args.args
    assert "SET updated_at=CURRENT_TIMESTAMP" in sql
    assert "SET customer_id" not in sql
    assert params == ("conversation-a", 1, "decentralized")


@pytest.mark.parametrize("method", ["authorize", "touch"])
def test_other_pattern_in_storage_is_rejected(storage, method):
    repo, conn, _ = storage
    conn.execute.return_value.fetchone.return_value = {**owner(), "pattern": "other"}
    with pytest.raises(ConversationConflict):
        getattr(repo, method)(conversation_id="conversation-a", authenticated_customer_id=1)
    assert conn.execute.call_count == 1


@pytest.mark.parametrize("method", ["register", "authorize", "touch"])
def test_storage_failure_rollback_and_safe_error(storage, method):
    repo, conn, tx = storage
    conn.execute.side_effect = RuntimeError("driver details must not escape")
    with pytest.raises(ConversationStorageError) as caught:
        if method == "register":
            register(repo)
        else:
            getattr(repo, method)(conversation_id="conversation-a", authenticated_customer_id=1)
    assert "driver details" not in str(caught.value)
    assert caught.value.__suppress_context__
    assert tx.__exit__.call_args.args[0] is RuntimeError


@pytest.mark.parametrize("changes", [dict(authenticated_customer_id=True), dict(authenticated_customer_id=0),
    dict(authenticated_customer_id=2**63), dict(conversation_id=" "), dict(thread_id=None), dict(pattern="hierarchical")])
def test_invalid_input_no_pool_access(storage, changes):
    repo, _, _ = storage
    with pytest.raises(ValueError):
        register(repo, **changes)
    repo.pool.connection.assert_not_called()


def test_identifiers_are_bound_as_values(storage):
    repo, conn, _ = storage
    conn.execute.return_value.fetchone.return_value = None
    identifier = "' OR 1=1 --"
    with pytest.raises(ConversationNotFound):
        repo.authorize(conversation_id=identifier, authenticated_customer_id=1)
    sql, params = conn.execute.call_args.args
    assert identifier not in sql and params == (identifier, 1)
