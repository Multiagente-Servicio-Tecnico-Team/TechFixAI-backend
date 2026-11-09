"""Opt-in real PostgreSQL test; preserves its unique test checkpoints.

PowerShell: set CHECKPOINT_POSTGRES_INTEGRATION=1 and the technical DSN,
then python -m pytest tests/test_checkpoint_postgres_integration.py -q.
Two sequential child processes write/read; no setup, migrations or LLM calls.
"""
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
from typing import TypedDict
from urllib.parse import urlsplit
from uuid import uuid4

import pytest


def worker(mode, thread_id):
    # Suppress third-party connection logs; never propagate raw driver errors.
    logging.disable(logging.CRITICAL)
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from app.database.decentralized_checkpoint import load_checkpoint_settings, build_checkpoint_resources
    from langgraph.graph import StateGraph, START, END

    settings = load_checkpoint_settings()
    if (not settings.dsn or urlsplit(settings.dsn).path != "/langgraph_checkpoint_test"
            or urlsplit(settings.dsn).username != "lg_test_runtime"
            or settings.schema != "langgraph_decentralized"):
        raise RuntimeError("Unexpected test target")
    with build_checkpoint_resources(settings) as resources:
        resources.pool.open(wait=True, timeout=10)
        with resources.pool.connection() as conn:
            identity = conn.execute("SELECT current_database() AS db, current_user AS role, current_schema() AS schema").fetchone()
            if identity != dict(db="langgraph_checkpoint_test", role="lg_test_runtime", schema="langgraph_decentralized"):
                raise RuntimeError("Unexpected server identity")
            # Effective privileges prevent this runtime role from modifying other
            # application relations, even if a future saver query were misrouted.
            unsafe = conn.execute("""SELECT EXISTS (
                SELECT 1 FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
                WHERE n.nspname NOT LIKE 'pg_%' AND n.nspname <> 'information_schema'
                AND n.nspname <> 'langgraph_decentralized' AND c.relkind IN ('r','p','v','m','f')
                AND pg_catalog.has_table_privilege(current_user,c.oid,'INSERT,UPDATE,DELETE,TRUNCATE')
            ) AS unsafe""").fetchone()["unsafe"]
            if unsafe:
                raise RuntimeError("Runtime can modify unrelated tables")
            catalog_sql = """SELECT n.nspname, c.relname, c.relkind FROM pg_catalog.pg_class c
                JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
                WHERE n.nspname NOT LIKE 'pg_%' AND n.nspname <> 'information_schema'
                ORDER BY n.nspname, c.relname"""
            before = conn.execute(catalog_sql).fetchall()
        config = {"configurable": {"thread_id": thread_id}}
        if mode == "write":
            class State(TypedDict):
                value: int
                marker: str

            builder = StateGraph(State)
            builder.add_node("increment", lambda state: {"value": state["value"] + 1})
            builder.add_edge(START, "increment")
            builder.add_edge("increment", END)
            graph = builder.compile(checkpointer=resources.saver)
            assert graph.invoke({"value": 41, "marker": thread_id}, config) == {"value": 42, "marker": thread_id}
        else:
            saved = resources.saver.get_tuple(config)
            assert saved is not None
            assert saved.checkpoint["channel_values"]["value"] == 42
            assert saved.checkpoint["channel_values"]["marker"] == thread_id
        with resources.pool.connection() as conn:
            assert conn.execute(catalog_sql).fetchall() == before
    print(json.dumps({"mode": mode, "pid": os.getpid(), "ok": True}))


@pytest.mark.skipif(os.environ.get("CHECKPOINT_POSTGRES_INTEGRATION") != "1",
                    reason="Explicit real PostgreSQL opt-in required")
def test_checkpoint_survives_independent_python_process():
    if not os.environ.get("DECENTRALIZED_CHECKPOINT_DSN"):
        pytest.fail("Missing technical test DSN", pytrace=False)
    thread_id = "infra-test-" + uuid4().hex
    results = []
    for mode in ("write", "read"):
        try:
            result = subprocess.run([sys.executable, "-B", str(Path(__file__).resolve()), mode, thread_id],
                                    capture_output=True, text=True, timeout=45)
        except subprocess.TimeoutExpired:
            pytest.fail(f"Checkpoint child timeout: {mode}", pytrace=False)
        if result.returncode != 0:
            pytest.fail(f"Checkpoint child failed: {mode}; details suppressed to protect credentials", pytrace=False)
        results.append(json.loads(result.stdout))
    assert results[0]["pid"] != results[1]["pid"]
    assert all(result["ok"] for result in results)
    print("Checkpoint recovered after writer process exited; thread_id=" + thread_id)


if __name__ == "__main__":
    try:
        worker(sys.argv[1], sys.argv[2])
    except Exception:
        print("Checkpoint integration worker failed", file=sys.stderr)
        sys.exit(1)
