"""Opt-in real pool/saver/owners/locks, deterministic graph and synthetic sessions.

Run only after authorization with DURABLE_HTTP_POSTGRES_INTEGRATION=1.
No setup or business SQL. Finally removes only this run's exact technical IDs.
"""
from contextlib import nullcontext
from pathlib import Path
import logging
import os
import subprocess
import sys
from types import SimpleNamespace
from urllib.parse import urlsplit
from uuid import uuid4

import pytest


def resources():
    from app.database.decentralized_checkpoint import load_checkpoint_settings, build_checkpoint_resources
    settings = load_checkpoint_settings()
    url = urlsplit(settings.dsn or "")
    if (url.path != "/langgraph_checkpoint_test" or url.username != "lg_test_runtime"
            or settings.schema != "langgraph_decentralized"):
        raise RuntimeError("Unexpected test target")
    return build_checkpoint_resources(settings)


opt_in = pytest.mark.skipif(os.getenv("DURABLE_HTTP_POSTGRES_INTEGRATION") != "1",
                           reason="Explicit authorization for real technical writes required")


@opt_in
def test_http_restart_ownership_and_closed_pool(monkeypatch):
    from typing import Annotated
    from typing_extensions import TypedDict
    from fastapi.testclient import TestClient
    from langchain_core.messages import AIMessage
    from langgraph.graph import StateGraph, START, END
    from langgraph.graph.message import add_messages
    from app.accounts.config import Settings
    import app.main as main
    identifier = "http-test-" + uuid4().hex
    monkeypatch.setattr(main, "uuid4", lambda: identifier)
    logging.disable(logging.CRITICAL)

    class State(TypedDict, total=False):
        messages: Annotated[list, add_messages]
        customer_id: int
        visits: int

    def build(saver):
        builder = StateGraph(State)
        def respond(state):
            visits = state.get("visits", 0) + 1
            return {"visits": visits, "messages": [AIMessage(content=f"visits={visits}")]}
        builder.add_node("respond", respond)
        builder.add_edge(START, "respond")
        builder.add_edge("respond", END)
        return builder.compile(checkpointer=saver)

    monkeypatch.setattr(main, "_build_decentralized_graph", build)

    class Guard:
        settings = Settings(database_url=None, auth_secret="s" * 48, secure_cookie=False)
        def require_customer(self, request):
            return SimpleNamespace(id=900000002 if request.headers.get("x-test-other") == "1" else 900000001)

    def application():
        return main.create_app(session_guard=Guard(), checkpoint_resources_factory=resources,
                               trace_context_factory=nullcontext)

    first = application()
    try:
        with TestClient(first) as client:
            response = client.post("/api/chat", json={"pattern": "decentralized", "message": "first"})
            assert response.status_code == 200 and response.json()["reply"] == "visits=1"
            pool = first.state.checkpoint_resources.pool
            with pool.connection() as conn:
                row = conn.execute("SELECT thread_id FROM langgraph_decentralized.conversation_owners WHERE conversation_id=%s", (identifier,)).fetchone()
                assert row["thread_id"] == identifier
        assert pool.closed
        second = application()  # fresh API state and fresh pool
        with TestClient(second) as client:
            body = dict(pattern="decentralized", message="second", conversation_id=identifier)
            response = client.post("/api/chat", json=body)
            assert response.status_code == 200 and response.json()["reply"] == "visits=2"
            assert client.post("/api/chat", json=body, headers={"x-test-other": "1"}).status_code == 404
            assert client.post("/api/chat", json={**body, "pattern": "hierarchical"}).status_code == 409
            from app.database.conversation_locks import ConversationLocks
            with resources() as external:
                external.pool.open(wait=True, timeout=10)
                with ConversationLocks(external.pool).hold(identifier):
                    busy = client.post("/api/chat", json=body)
                    assert busy.status_code == 409 and busy.json()["code"] == "conversation_busy"
            second.state.checkpoint_resources.pool.close()
            assert client.post("/api/chat", json=body).status_code == 503
    finally:
        try:
            with resources() as cleanup:
                cleanup.pool.open(wait=True, timeout=10)
                with cleanup.pool.connection() as conn, conn.transaction():
                    for table in ("checkpoint_writes", "checkpoint_blobs", "checkpoints"):
                        conn.execute(f"DELETE FROM langgraph_decentralized.{table} WHERE thread_id=%s", (identifier,))
                    conn.execute("DELETE FROM langgraph_decentralized.conversation_owners WHERE conversation_id=%s AND thread_id=%s", (identifier, identifier))
        finally:
            logging.disable(logging.NOTSET)


@opt_in
def test_locks_between_python_processes():
    identifier = "lock-test-" + uuid4().hex
    path = str(Path(__file__).resolve())
    holder = subprocess.Popen([sys.executable, "-B", path, "hold", identifier],
                              stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        # communicate via reader thread so failed startup never hangs the suite.
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor() as executor:
            ready = executor.submit(holder.stdout.readline)
            try:
                assert ready.result(timeout=20).strip() == "HELD"
            except Exception:
                holder.kill()
                raise
        for thread, expected in ((identifier, "BUSY"), (identifier + "-independent", "FREE")):
            result = subprocess.run([sys.executable, "-B", path, "try", thread], capture_output=True, text=True, timeout=20)
            assert result.returncode == 0 and result.stdout.strip() == expected
        holder.communicate("release\n", timeout=20)
        assert holder.returncode == 0
        result = subprocess.run([sys.executable, "-B", path, "try", identifier], capture_output=True, text=True, timeout=20)
        assert result.returncode == 0 and result.stdout.strip() == "FREE"
        # Abrupt process death closes its connection and releases session lock.
        holder = subprocess.Popen([sys.executable, "-B", path, "hold", identifier],
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        with ThreadPoolExecutor() as executor:
            ready = executor.submit(holder.stdout.readline)
            try:
                assert ready.result(timeout=20).strip() == "HELD"
            except Exception:
                holder.kill()
                raise
        holder.kill()
        holder.communicate(timeout=20)
        result = subprocess.run([sys.executable, "-B", path, "try", identifier], capture_output=True, text=True, timeout=20)
        assert result.returncode == 0 and result.stdout.strip() == "FREE"
    finally:
        if holder.poll() is None:
            holder.kill()
        holder.communicate(timeout=20)


def child(mode, identifier):
    logging.disable(logging.CRITICAL)
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from app.database.conversation_locks import ConversationLocks, ConversationBusy
    with resources() as storage:
        storage.pool.open(wait=True, timeout=10)
        try:
            with ConversationLocks(storage.pool).hold(identifier):
                print("HELD" if mode == "hold" else "FREE", flush=True)
                if mode == "hold":
                    sys.stdin.readline()
        except ConversationBusy:
            print("BUSY", flush=True)


if __name__ == "__main__":
    try:
        child(sys.argv[1], sys.argv[2])
    except Exception:
        sys.exit(1)
