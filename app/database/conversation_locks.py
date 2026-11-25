"""Session advisory locks on an exclusively checked-out pool connection."""
from contextlib import contextmanager


class ConversationBusy(RuntimeError):
    pass


class ConversationLockStorageError(RuntimeError):
    pass


class ConversationLocks:
    def __init__(self, pool):
        self.pool = pool

    @contextmanager
    def hold(self, thread_id):
        if not isinstance(thread_id, str) or not thread_id.strip():
            raise ValueError("Thread obligatorio")
        conn = None
        acquired = False
        body_error = False
        # Stable PostgreSQL-side hash; never Python's process-dependent hash().
        key = "decentralized-conversation:" + thread_id
        try:
            try:
                context = self.pool.connection()
                conn = context.__enter__()
                acquired = conn.execute(
                    "SELECT pg_catalog.pg_try_advisory_lock(pg_catalog.hashtextextended(%s, 0)) AS acquired",
                    (key,)).fetchone()["acquired"] is True
            except Exception:
                if conn is not None:
                    conn.close()  # ambiguous acquisition must not return a live lock
                raise ConversationLockStorageError("No fue posible bloquear la conversación") from None
            if not acquired:
                raise ConversationBusy("Conversación ocupada")
            try:
                yield
            except BaseException:
                body_error = True
                raise
            finally:
                try:
                    released = conn.execute(
                        "SELECT pg_catalog.pg_advisory_unlock(pg_catalog.hashtextextended(%s, 0)) AS released",
                        (key,)).fetchone()["released"] is True
                    if not released:
                        raise RuntimeError()
                except Exception:
                    conn.close()  # closing session releases all its advisory locks
                    if not body_error:
                        raise ConversationLockStorageError("No fue posible liberar la conversación") from None
        finally:
            if conn is not None:
                try:
                    context.__exit__(None, None, None)
                except Exception:
                    conn.close()
                    if not body_error:
                        raise ConversationLockStorageError("No fue posible devolver conexión de coordinación") from None
