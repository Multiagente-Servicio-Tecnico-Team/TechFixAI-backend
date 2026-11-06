from unittest.mock import MagicMock
import pytest
from app.database.conversation_locks import ConversationLocks, ConversationBusy, ConversationLockStorageError


def storage(rows):
    pool, conn = MagicMock(), MagicMock()
    pool.connection.return_value.__enter__.return_value = conn
    conn.execute.return_value.fetchone.side_effect = rows
    return ConversationLocks(pool), pool, conn


@pytest.mark.parametrize("failure", [False, True])
def test_lock_held_for_body_and_released_after_exception(failure):
    locks, pool, conn = storage([{"acquired": True}, {"released": True}])
    def run():
        with locks.hold("thread-a"):
            assert conn.execute.call_count == 1
            pool.connection.return_value.__exit__.assert_not_called()
            if failure:
                raise ValueError("body")
    if failure:
        with pytest.raises(ValueError):
            run()
    else:
        run()
    assert "pg_advisory_unlock" in conn.execute.call_args.args[0]
    pool.connection.return_value.__exit__.assert_called_once()


def test_busy_does_not_enter_body_or_unlock():
    locks, pool, conn = storage([{"acquired": False}])
    with pytest.raises(ConversationBusy):
        with locks.hold("thread-a"):
            pytest.fail("must not enter")
    assert conn.execute.call_count == 1
    pool.connection.return_value.__exit__.assert_called_once()


def test_ambiguous_acquisition_closes_session():
    locks, _, conn = storage([])
    conn.execute.side_effect = RuntimeError("sensitive details")
    with pytest.raises(ConversationLockStorageError) as error:
        with locks.hold("thread-a"):
            pytest.fail("must not enter")
    assert "sensitive" not in str(error.value)
    conn.close.assert_called_once()


def test_failed_unlock_closes_connection():
    locks, _, conn = storage([{"acquired": True}, {"released": False}])
    with pytest.raises(ConversationLockStorageError):
        with locks.hold("thread-a"):
            pass
    conn.close.assert_called_once()


def test_independent_threads_have_independent_keys():
    locks, _, conn = storage([{"acquired": True}, {"released": True}, {"acquired": True}, {"released": True}])
    for thread in ("a", "b"):
        with locks.hold(thread):
            pass
    assert conn.execute.call_args_list[0].args[1] != conn.execute.call_args_list[2].args[1]


def test_two_coordinators_share_lock_and_independent_thread_runs():
    # Model PostgreSQL session lock semantics, not actual database concurrency.
    from contextlib import contextmanager
    held = set()
    class Pool:
        @contextmanager
        def connection(self):
            class Connection:
                def execute(self, sql, params):
                    key = params[0]
                    if "pg_try_advisory_lock" in sql:
                        acquired = key not in held
                        if acquired:
                            held.add(key)
                        row = {"acquired": acquired}
                    else:
                        held.remove(key)
                        row = {"released": True}
                    return type("Cursor", (), {"fetchone": lambda self: row})()
            yield Connection()
    first, second = ConversationLocks(Pool()), ConversationLocks(Pool())
    with first.hold("same"):
        with pytest.raises(ConversationBusy):
            with second.hold("same"):
                pytest.fail("same thread overlap")
        with second.hold("different"):
            assert len(held) == 2
    with second.hold("same"):
        assert len(held) == 1
    assert not held
