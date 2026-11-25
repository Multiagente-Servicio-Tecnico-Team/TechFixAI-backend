"""Opt-in PostgreSQL ownership test; retains only uniquely named technical rows.

Requires CONVERSATION_OWNERS_POSTGRES_INTEGRATION=1, technical test DSN,
and CHECKPOINT_TEST_CUSTOMER_ID / CHECKPOINT_TEST_OTHER_CUSTOMER_ID supplied
by the operator for two existing authorized test customers. Never creates users.
"""
from contextlib import contextmanager
import logging
import os
from urllib.parse import urlsplit
from uuid import uuid4

import pytest

from app.database.decentralized_checkpoint import load_checkpoint_settings, build_checkpoint_resources
from app.database.conversation_owners import (
    ConversationOwnersRepository, ConversationConflict, ConversationNotFound,
    ConversationStorageError,
)


@pytest.mark.skipif(os.getenv("CONVERSATION_OWNERS_POSTGRES_INTEGRATION") != "1",
                    reason="Explicit PostgreSQL ownership integration opt-in required")
def test_real_conversation_ownership():
    settings = load_checkpoint_settings()
    if not settings.dsn:
        pytest.fail("Missing technical test DSN", pytrace=False)
    parsed = urlsplit(settings.dsn)
    if (parsed.path != "/langgraph_checkpoint_test" or parsed.username != "lg_test_runtime"
            or settings.schema != "langgraph_decentralized"):
        pytest.fail("Unexpected test target", pytrace=False)
    try:
        customer = int(os.environ["CHECKPOINT_TEST_CUSTOMER_ID"])
        other = int(os.environ["CHECKPOINT_TEST_OTHER_CUSTOMER_ID"])
        if customer <= 0 or other <= 0 or customer == other:
            raise ValueError
    except (KeyError, ValueError):
        pytest.fail("Two distinct authorized existing test customer IDs required", pytrace=False)
    # IDs are an operator-provided precondition, not fabricated customers. The
    # technical table intentionally has no business-user FK or authentication.
    identifier = "owners-test-" + uuid4().hex
    previous_logging = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    try:
        with build_checkpoint_resources(settings) as resources:
            resources.pool.open(wait=True, timeout=10)
            with resources.pool.connection() as conn:
                identity = conn.execute("SELECT current_database() AS db, current_user AS role, current_schema() AS schema").fetchone()
                assert identity == dict(db="langgraph_checkpoint_test", role="lg_test_runtime", schema="langgraph_decentralized")
            repo = ConversationOwnersRepository(resources.pool)
            args = dict(conversation_id=identifier, thread_id=identifier, authenticated_customer_id=customer)
            first = repo.register(**args)
            assert repo.register(**args) == first
            assert repo.authorize(conversation_id=identifier, authenticated_customer_id=customer) == first
            for conversation_id in (identifier, identifier + "-absent"):
                with pytest.raises(ConversationNotFound, match="Conversación no encontrada"):
                    repo.authorize(conversation_id=conversation_id, authenticated_customer_id=other)
            for changes in (dict(authenticated_customer_id=other), dict(thread_id=identifier + "-other"),
                            dict(conversation_id=identifier + "-collision"), dict(pattern="hierarchical")):
                with pytest.raises(ConversationConflict):
                    repo.register(**{**args, **changes})
            updated = repo.touch(conversation_id=identifier, authenticated_customer_id=customer)
            assert updated["updated_at"] > first["updated_at"]
            assert all(updated[key] == first[key] for key in first if key != "updated_at")

            # Execute a real INSERT through the repository, then raise before
            # returning its cursor: its transaction must roll back that INSERT.
            class FailingPool:
                @contextmanager
                def connection(self):
                    with resources.pool.connection() as connection:
                        class Proxy:
                            def transaction(self):
                                return connection.transaction()

                            def execute(self, query, params):
                                connection.execute(query, params)
                                raise RuntimeError("Injected post-insert failure")
                        yield Proxy()

            with pytest.raises(ConversationStorageError):
                ConversationOwnersRepository(FailingPool()).register(
                    **{**args, "conversation_id": identifier + "-rollback", "thread_id": identifier + "-rollback"})
            with resources.pool.connection() as conn:
                count = conn.execute("SELECT count(*) AS count FROM langgraph_decentralized.conversation_owners WHERE conversation_id=%s OR thread_id=%s",
                                     (identifier, identifier)).fetchone()["count"]
                assert count == 1
                assert conn.execute("SELECT count(*) AS count FROM langgraph_decentralized.conversation_owners WHERE conversation_id=%s",
                                    (identifier + "-rollback",)).fetchone()["count"] == 0
            assert repo.authorize(conversation_id=identifier, authenticated_customer_id=customer)["customer_id"] == customer
    except (AssertionError, ConversationConflict, ConversationNotFound):
        pytest.fail("Ownership integration assertion failed; details suppressed", pytrace=False)
    except Exception:
        pytest.fail("Ownership integration storage failure; details suppressed", pytrace=False)
    finally:
        logging.disable(previous_logging)
