"""Explicit technical migration entry point. Default CLI only prints SQL."""
import argparse
from importlib.metadata import version
import os
import re

from app.database.decentralized_checkpoint import CheckpointSettings


ADAPTER_VERSION = "3.1.2"
TECHNICAL_SCHEMA = "langgraph_decentralized"


class PreflightError(RuntimeError):
    """Fixed, credential-free operator guidance."""


def validate_preflight(conn, runtime_conn, migration_role, runtime_role):
    """Read-only checks, fail closed before any DDL.

    Nonempty existing schemas require manual compatibility review: names alone
    cannot prove compatible columns, constraints, triggers and migration history.
    """
    identity_sql = """SELECT current_user AS role, session_user AS session_role,
        current_database() AS database, pg_catalog.inet_server_addr()::text AS server_address,
        pg_catalog.inet_server_port() AS server_port,
        r.rolsuper, r.rolcreatedb, r.rolcreaterole,
        r.rolreplication, r.rolbypassrls FROM pg_catalog.pg_roles r
        WHERE r.rolname = current_user"""
    migration = conn.execute(identity_sql).fetchone()
    runtime = runtime_conn.execute(identity_sql).fetchone()
    for row, expected in ((migration, migration_role), (runtime, runtime_role)):
        if (not row or row["role"] != expected or row["session_role"] != expected
                or any(row[key] for key in ("rolsuper", "rolcreatedb", "rolcreaterole",
                                            "rolreplication", "rolbypassrls"))):
            raise PreflightError("Identidad o privilegios elevados no autorizados")
    if (migration_role == runtime_role or any(migration[key] != runtime[key]
            for key in ("database", "server_address", "server_port"))):
        raise PreflightError("Roles deben ser distintos y usar la misma base técnica")
    for source, target in ((migration_role, runtime_role), (runtime_role, migration_role)):
        if conn.execute("SELECT pg_catalog.pg_has_role(%s, %s, 'MEMBER') AS member",
                        (source, target)).fetchone()["member"]:
            raise PreflightError("Roles de migración y ejecución no pueden heredarse entre sí")
    # Effective privileges include inherited grants and PUBLIC. Reject access to
    # business relations and creation in any nontechnical application schema.
    unsafe_sql = """SELECT EXISTS (
        SELECT 1 FROM pg_catalog.pg_namespace n
        WHERE n.nspname NOT LIKE 'pg_%%' AND n.nspname <> 'information_schema'
        AND n.nspname <> %s AND pg_catalog.has_schema_privilege(current_user, n.oid, 'CREATE')
        UNION ALL
        SELECT 1 FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname NOT LIKE 'pg_%%' AND n.nspname <> 'information_schema'
        AND n.nspname <> %s AND c.relkind IN ('r','p','v','m','f')
        AND (c.relowner = (SELECT oid FROM pg_catalog.pg_roles WHERE rolname=current_user)
             OR pg_catalog.has_table_privilege(current_user, c.oid,
                 'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER'))
        UNION ALL
        SELECT 1 FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname NOT LIKE 'pg_%%' AND n.nspname <> 'information_schema'
        AND n.nspname <> %s AND c.relkind = 'S'
        AND pg_catalog.has_sequence_privilege(current_user, c.oid, 'USAGE,SELECT,UPDATE')
    ) AS unsafe"""
    for connection in (conn, runtime_conn):
        if connection.execute(unsafe_sql, (TECHNICAL_SCHEMA,) * 3).fetchone()["unsafe"]:
            raise PreflightError("Rol con acceso no autorizado fuera del esquema técnico")
    if runtime_conn.execute("SELECT pg_catalog.has_database_privilege(current_user, current_database(), 'CREATE') AS allowed").fetchone()["allowed"]:
        raise PreflightError("El rol de ejecución no puede crear esquemas")
    schema = conn.execute("""SELECT n.oid, pg_catalog.pg_get_userbyid(n.nspowner) AS owner
        FROM pg_catalog.pg_namespace n WHERE n.nspname=%s""", (TECHNICAL_SCHEMA,)).fetchone()
    if schema:
        if schema["owner"] != migration_role:
            raise PreflightError("Propietario del esquema técnico no autorizado")
        if runtime_conn.execute("SELECT pg_catalog.has_schema_privilege(current_user, %s, 'CREATE') AS allowed",
                                (schema["oid"],)).fetchone()["allowed"]:
            raise PreflightError("El rol de ejecución no puede crear objetos técnicos")
        invalid = conn.execute("""SELECT EXISTS (SELECT 1 FROM pg_catalog.pg_index i
            JOIN pg_catalog.pg_class c ON c.oid=i.indrelid
            WHERE c.relnamespace=%s AND (NOT i.indisvalid OR NOT i.indisready)) AS invalid""",
                               (schema["oid"],)).fetchone()["invalid"]
        if invalid:
            raise PreflightError("Índice técnico inválido: detener; un DBA debe inspeccionar pg_index y planificar recuperación manual antes de reintentar")
        occupied = conn.execute("""SELECT EXISTS (
            SELECT 1 FROM pg_catalog.pg_class WHERE relnamespace=%s
            UNION ALL SELECT 1 FROM pg_catalog.pg_proc WHERE pronamespace=%s
            UNION ALL SELECT 1 FROM pg_catalog.pg_type WHERE typnamespace=%s
        ) AS occupied""", (schema["oid"],) * 3).fetchone()["occupied"]
        if occupied:
            raise PreflightError("Esquema técnico no vacío: requiere revisión manual de compatibilidad; no se modificará")
    elif not conn.execute("SELECT pg_catalog.has_database_privilege(current_user, current_database(), 'CREATE') AS allowed").fetchone()["allowed"]:
        raise PreflightError("El rol de migración no puede crear el esquema técnico")
    return schema is not None


def migration_plan(schema="langgraph_decentralized"):
    """No connection; use the exact installed, reviewed adapter migrations."""
    CheckpointSettings(schema=schema)
    if schema != TECHNICAL_SCHEMA:
        raise ValueError("Solo se permite langgraph_decentralized")
    if len(schema) > 63:
        raise ValueError("Esquema técnico demasiado largo")
    if version("langgraph-checkpoint-postgres") != ADAPTER_VERSION:
        raise RuntimeError("Versión del adaptador no revisada")
    from langgraph.checkpoint.postgres import PostgresSaver
    return [
        f'CREATE SCHEMA IF NOT EXISTS "{schema}";',
        f'SET search_path TO "{schema}";',
        *PostgresSaver.MIGRATIONS,
        f'''CREATE TABLE IF NOT EXISTS "{schema}".conversation_owners (
    conversation_id TEXT PRIMARY KEY CHECK (length(conversation_id) > 0),
    thread_id TEXT NOT NULL UNIQUE CHECK (length(thread_id) > 0),
    customer_id BIGINT NOT NULL CHECK (customer_id > 0),
    pattern TEXT NOT NULL CHECK (pattern = 'decentralized'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);''',
    ]


def initialize_technical_storage(*, migration_dsn, schema="langgraph_decentralized",
                                 confirmed=False, runtime_dsn=None,
                                 migration_role=None, runtime_role=None):
    """Only called by an explicitly authorized operator, never API startup.

    Separate migration DSN is mandatory. Session advisory lock serializes setup.
    Autocommit is required by the adapter's concurrent index migrations; a failure
    may leave completed migration steps, tracked by checkpoint_migrations.
    """
    if confirmed is not True:
        raise ValueError("Inicialización requiere confirmación explícita")
    settings = CheckpointSettings(dsn=migration_dsn, schema=schema)
    if not settings.dsn:
        raise ValueError("Falta DSN de migración independiente")
    plan = migration_plan(schema)
    if not runtime_dsn or not migration_role or not runtime_role:
        raise ValueError("Se requieren DSN de ejecución y nombres explícitos de ambos roles")
    CheckpointSettings(dsn=runtime_dsn, schema=schema)
    import psycopg
    from psycopg.rows import dict_row
    from langgraph.checkpoint.postgres import PostgresSaver
    stage = "conexion_migracion"
    try:
        with psycopg.connect(settings.dsn, autocommit=True, row_factory=dict_row,
                             connect_timeout=settings.connect_timeout) as conn:
            # Lock released automatically when this dedicated connection closes.
            stage = "bloqueo"
            conn.execute("SELECT pg_advisory_lock(hashtextextended(%s, 0))",
                         ("decentralized_checkpoint_init:" + schema,))
            stage = "conexion_ejecucion"
            with psycopg.connect(runtime_dsn, autocommit=True, row_factory=dict_row,
                                 connect_timeout=settings.connect_timeout) as runtime_conn:
                stage = "preflight"
                schema_exists = validate_preflight(conn, runtime_conn, migration_role, runtime_role)
            # PostgreSQL checks database CREATE even with IF NOT EXISTS. An
            # already validated schema needs no database-level creation grant.
            if not schema_exists:
                stage = "crear_esquema"
                conn.execute(plan[0])
            stage = "search_path"
            conn.execute(plan[1])
            stage = "setup_adaptador"
            PostgresSaver(conn).setup()
            stage = "registro_propiedad"
            conn.execute(plan[-1])
    except PreflightError:
        raise
    except Exception as error:
        # Never include exception text, diag fields, queries or connection info.
        code = getattr(error, "sqlstate", None)
        safe_code = code if isinstance(code, str) and re.fullmatch(r"[0-9A-Z]{5}", code) else "no_disponible"
        if isinstance(error, psycopg.Error):
            category = "sql_servidor" if safe_code != "no_disponible" else "psycopg_cliente"
        elif isinstance(error, (KeyError, TypeError, IndexError, AttributeError)):
            category = "estructura_resultado"
        else:
            category = "python_no_clasificado"
        raise RuntimeError(f"No fue posible inicializar almacenamiento técnico; etapa={stage}; categoria={category}; SQLSTATE={safe_code}") from None


def main():
    parser = argparse.ArgumentParser(description="Revisión o inicialización técnica explícita")
    parser.add_argument("--schema", default=TECHNICAL_SCHEMA, choices=[TECHNICAL_SCHEMA])
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if args.apply:
        initialize_technical_storage(
            migration_dsn=os.environ.get("DECENTRALIZED_CHECKPOINT_MIGRATION_DSN"),
            schema=args.schema, confirmed=True,
            runtime_dsn=os.environ.get("DECENTRALIZED_CHECKPOINT_DSN"),
            migration_role=os.environ.get("DECENTRALIZED_CHECKPOINT_MIGRATION_ROLE"),
            runtime_role=os.environ.get("DECENTRALIZED_CHECKPOINT_RUNTIME_ROLE"))
    else:
        print("-- PREVIEW ONLY: adapter migrations; setup tracks versions separately.")
        print("\n".join(migration_plan(args.schema)))


if __name__ == "__main__":
    main()
