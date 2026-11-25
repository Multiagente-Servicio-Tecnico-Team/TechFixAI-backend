"""No database: installed constructors and mocked migration execution."""
from unittest.mock import MagicMock

import pytest
import psycopg
from langgraph.checkpoint.postgres import PostgresSaver

from app.database.decentralized_checkpoint import CheckpointSettings, build_checkpoint_resources
from app.database import decentralized_checkpoint_init as initializer


def test_installed_objects_without_connection(monkeypatch):
    connect = MagicMock(side_effect=AssertionError("No network allowed"))
    monkeypatch.setattr(psycopg, "connect", connect)
    with build_checkpoint_resources(CheckpointSettings(dsn="postgresql://localhost/test")) as resources:
        assert isinstance(resources.saver, PostgresSaver)
        assert resources.pool.closed
    connect.assert_not_called()


def test_preview_contains_only_technical_objects(monkeypatch):
    connect = MagicMock()
    monkeypatch.setattr(psycopg, "connect", connect)
    plan = initializer.migration_plan()
    assert plan[2:-1] == PostgresSaver.MIGRATIONS
    assert '"langgraph_decentralized".conversation_owners' in plan[-1]
    for field in ("conversation_id", "thread_id", "customer_id", "pattern", "created_at", "updated_at"):
        assert field in plan[-1]
    assert "UNIQUE" in plan[-1] and "decentralized" in plan[-1]
    assert "REFERENCES" not in plan[-1]
    connect.assert_not_called()


@pytest.mark.parametrize("schema", ["business", "public", "pg_catalog", "x; DROP TABLE users", "x" * 64])
def test_invalid_schema(schema):
    with pytest.raises(ValueError):
        initializer.migration_plan(schema)


def test_version_change_requires_review(monkeypatch):
    monkeypatch.setattr(initializer, "version", lambda _: "99.0")
    with pytest.raises(RuntimeError, match="no revisada"):
        initializer.migration_plan()


@pytest.mark.parametrize("confirmed,dsn", [(False, "postgresql://localhost/test"), (True, None)])
def test_requires_confirmation_and_migration_dsn(monkeypatch, confirmed, dsn):
    connect = MagicMock()
    monkeypatch.setattr(psycopg, "connect", connect)
    with pytest.raises(ValueError):
        initializer.initialize_technical_storage(migration_dsn=dsn, confirmed=confirmed)
    connect.assert_not_called()


@pytest.mark.parametrize("fail", [False, True])
def test_migration_order_and_cleanup(monkeypatch, fail):
    monkeypatch.setattr(initializer, "validate_preflight", MagicMock(return_value=False))
    conn = MagicMock()
    context = MagicMock()
    context.__enter__.return_value = conn
    connect = MagicMock(return_value=context)
    monkeypatch.setattr(psycopg, "connect", connect)
    setup = MagicMock()
    monkeypatch.setattr(PostgresSaver, "setup", setup)
    if fail:
        setup.side_effect = RuntimeError("secret-password")
        with pytest.raises(RuntimeError) as error:
            initializer.initialize_technical_storage(migration_dsn="postgresql://localhost/test", confirmed=True,
                runtime_dsn="postgresql://localhost/test", migration_role="migrator", runtime_role="runtime")
        assert "secret-password" not in str(error.value)
        assert error.value.__suppress_context__
        assert conn.execute.call_count == 3
    else:
        initializer.initialize_technical_storage(migration_dsn="postgresql://localhost/test", confirmed=True,
            runtime_dsn="postgresql://localhost/test", migration_role="migrator", runtime_role="runtime")
        setup.assert_called_once()
        assert conn.execute.call_count == 4
        assert "pg_advisory_lock" in conn.execute.call_args_list[0].args[0]
        assert "CREATE SCHEMA IF NOT EXISTS" in conn.execute.call_args_list[1].args[0]
        assert "SET search_path" in conn.execute.call_args_list[2].args[0]
        assert "conversation_owners" in conn.execute.call_args_list[3].args[0]
    assert connect.call_args.kwargs["autocommit"] is True
    assert context.__exit__.call_count == 2


def test_cli_defaults_to_preview(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["initializer"])
    apply = MagicMock()
    monkeypatch.setattr(initializer, "initialize_technical_storage", apply)
    initializer.main()
    assert "PREVIEW ONLY" in capsys.readouterr().out
    apply.assert_not_called()


def preflight_connections(schema=None, invalid=False, occupied=False):
    def identity(role):
        return dict(role=role, session_role=role, database="technical", server_address="127.0.0.1", server_port=5432, rolsuper=False,
                    rolcreatedb=False, rolcreaterole=False, rolreplication=False, rolbypassrls=False)
    migration_rows = [identity("migrator"), {"member": False}, {"member": False},
                      {"unsafe": False}, schema]
    runtime_rows = [identity("runtime"), {"unsafe": False}, {"allowed": False}]
    if schema:
        runtime_rows += [{"allowed": False}]
        migration_rows += [{"invalid": invalid}, {"occupied": occupied}]
    else:
        migration_rows += [{"allowed": True}]
    conn, runtime = MagicMock(), MagicMock()
    conn.execute.return_value.fetchone.side_effect = migration_rows
    runtime.execute.return_value.fetchone.side_effect = runtime_rows
    return conn, runtime, migration_rows, runtime_rows


@pytest.mark.parametrize("schema", [None, {"oid": 123, "owner": "migrator"}])
def test_preflight_accepts_pristine_authorized_schema(schema):
    conn, runtime, _, _ = preflight_connections(schema)
    initializer.validate_preflight(conn, runtime, "migrator", "runtime")
    for connection in (conn, runtime):
        assert all(call.args[0].lstrip().startswith("SELECT") for call in connection.execute.call_args_list)


@pytest.mark.parametrize("case", ["owner", "invalid", "occupied", "superuser", "identity",
                                     "membership", "business_access", "runtime_ddl", "database", "server", "migration_create"])
def test_preflight_rejects_unsafe_state(case):
    schema = {"oid": 123, "owner": "other" if case == "owner" else "migrator"}
    conn, runtime, rows, runtime_rows = preflight_connections(
        None if case == "migration_create" else schema,
        invalid=case == "invalid", occupied=case == "occupied")
    if case == "superuser":
        runtime_rows[0]["rolsuper"] = True
    if case == "identity":
        rows[0]["session_role"] = "other"
    if case == "membership":
        rows[1]["member"] = True
    if case == "business_access":
        rows[3]["unsafe"] = True
    if case == "runtime_ddl":
        runtime_rows[2]["allowed"] = True
    if case == "database":
        runtime_rows[0]["database"] = "other"
    if case == "server":
        runtime_rows[0]["server_address"] = "other"
    if case == "migration_create":
        rows[-1]["allowed"] = False
    with pytest.raises(initializer.PreflightError) as error:
        initializer.validate_preflight(conn, runtime, "migrator", "runtime")
    if case == "invalid":
        assert "recuperación manual" in str(error.value)


def test_preflight_failure_never_reaches_ddl_or_setup(monkeypatch):
    conn = MagicMock()
    context = MagicMock()
    context.__enter__.return_value = conn
    monkeypatch.setattr(psycopg, "connect", MagicMock(return_value=context))
    monkeypatch.setattr(initializer, "validate_preflight", MagicMock(side_effect=initializer.PreflightError("Rol rechazado")))
    setup = MagicMock()
    monkeypatch.setattr(PostgresSaver, "setup", setup)
    with pytest.raises(initializer.PreflightError):
        initializer.initialize_technical_storage(migration_dsn="postgresql://localhost/test", confirmed=True,
            runtime_dsn="postgresql://localhost/test", migration_role="migrator", runtime_role="runtime")
    setup.assert_not_called()
    assert conn.execute.call_count == 1  # advisory lock only, no DDL


def test_cli_rejects_other_schema_without_connection(monkeypatch):
    monkeypatch.setattr("sys.argv", ["initializer", "--schema", "business"])
    connect = MagicMock()
    monkeypatch.setattr(psycopg, "connect", connect)
    with pytest.raises(SystemExit):
        initializer.main()
    connect.assert_not_called()


@pytest.mark.parametrize("exists", [False, True])
def test_schema_creation_only_when_missing(monkeypatch, exists):
    conn = MagicMock()
    context = MagicMock()
    context.__enter__.return_value = conn
    monkeypatch.setattr(psycopg, "connect", MagicMock(return_value=context))
    monkeypatch.setattr(initializer, "validate_preflight", MagicMock(return_value=exists))
    setup = MagicMock()
    monkeypatch.setattr(PostgresSaver, "setup", setup)
    initializer.initialize_technical_storage(migration_dsn="postgresql://localhost/test", confirmed=True,
        runtime_dsn="postgresql://localhost/test", migration_role="migrator", runtime_role="runtime")
    statements = [call.args[0] for call in conn.execute.call_args_list]
    assert any("CREATE SCHEMA" in sql for sql in statements) is (not exists)
    assert any("SET search_path" in sql for sql in statements)
    setup.assert_called_once()


@pytest.mark.parametrize("code,expected", [("42501", "42501"), ("secret-password", "no_disponible"), (None, "no_disponible")])
def test_sanitized_stage_and_sqlstate(monkeypatch, code, expected):
    conn = MagicMock()
    context = MagicMock()
    context.__enter__.return_value = conn
    monkeypatch.setattr(psycopg, "connect", MagicMock(return_value=context))
    monkeypatch.setattr(initializer, "validate_preflight", MagicMock(return_value=True))
    error = RuntimeError("postgresql://user:secret-password@host/db")
    error.sqlstate = code
    monkeypatch.setattr(PostgresSaver, "setup", MagicMock(side_effect=error))
    with pytest.raises(RuntimeError) as caught:
        initializer.initialize_technical_storage(migration_dsn="postgresql://localhost/test", confirmed=True,
            runtime_dsn="postgresql://localhost/test", migration_role="migrator", runtime_role="runtime")
    assert "etapa=setup_adaptador" in str(caught.value)
    assert f"SQLSTATE={expected}" in str(caught.value)
    assert "secret-password" not in str(caught.value)
    assert caught.value.__suppress_context__


def test_real_psycopg_parameter_parser_preflight_queries():
    # Installed driver's parser, offline: mocks alone miss malformed placeholders.
    from psycopg._queries import _query2pg_nocache
    conn, runtime, _, _ = preflight_connections({"oid": 123, "owner": "migrator"})
    initializer.validate_preflight(conn, runtime, "migrator", "runtime")
    unsafe = None
    for connection in (conn, runtime):
        for call in connection.execute.call_args_list:
            if len(call.args) == 2:
                query, params = call.args
                converted, formats, _, _ = _query2pg_nocache(query.encode(), "utf-8")
                assert len(formats) == len(params)
                if "AS unsafe" in query:
                    unsafe = query
                    assert converted.count(b"'pg_%'") == 3
    assert unsafe is not None
    with pytest.raises(psycopg.ProgrammingError) as caught:
        _query2pg_nocache(unsafe.replace("pg_%%", "pg_%").encode(), "utf-8")
    assert caught.value.sqlstate is None


@pytest.mark.parametrize("error,category", [
    (psycopg.ProgrammingError("secret-password"), "psycopg_cliente"),
    (psycopg.errors.InsufficientPrivilege("secret-password"), "sql_servidor"),
    (KeyError("secret-password"), "estructura_resultado"),
    (TypeError("secret-password"), "estructura_resultado"),
])
def test_safe_preflight_error_categories(monkeypatch, error, category):
    context = MagicMock()
    monkeypatch.setattr(psycopg, "connect", MagicMock(return_value=context))
    monkeypatch.setattr(initializer, "validate_preflight", MagicMock(side_effect=error))
    setup = MagicMock()
    monkeypatch.setattr(PostgresSaver, "setup", setup)
    with pytest.raises(RuntimeError) as caught:
        initializer.initialize_technical_storage(migration_dsn="postgresql://localhost/test", confirmed=True,
            runtime_dsn="postgresql://localhost/test", migration_role="migrator", runtime_role="runtime")
    assert "etapa=preflight" in str(caught.value)
    assert f"categoria={category}" in str(caught.value)
    assert "secret-password" not in str(caught.value)
    setup.assert_not_called()
