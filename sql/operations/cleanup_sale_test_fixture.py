"""Preflight and explicitly gated cleanup for the reviewed local SALE test fixture.

Default behavior is read-only. Execution requires an exact database allow-list,
an existing backup file, a literal target confirmation, and an exact manifest
match. This tool is intentionally not called from application startup/migrations.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any

from sqlalchemy import create_engine, text


DEFAULT_MANIFEST = Path(__file__).with_name("sale-test-fixture-2026-11-03.json")
DEPENDENCY_QUERIES = {
    "logistics_records": "SELECT id FROM logistics_records WHERE ticket_id=ANY(:ids) ORDER BY id",
    "payments": "SELECT id FROM payments WHERE ticket_id=ANY(:ids) ORDER BY id",
    "quotes": "SELECT id FROM quotes WHERE ticket_id=ANY(:ids) ORDER BY id",
    "warranties": "SELECT id FROM warranties WHERE ticket_id=ANY(:ids) ORDER BY id",
    "refunds": "SELECT r.id FROM refunds r JOIN payments p ON p.id=r.payment_id WHERE p.ticket_id=ANY(:ids) ORDER BY r.id",
    "ticket_audit_events": "SELECT id FROM ticket_audit_events WHERE ticket_id=ANY(:ids) ORDER BY id",
    "warranty_claims": "SELECT id FROM warranty_claims WHERE ticket_id=ANY(:ids) ORDER BY id",
}
DELETE_ORDER = (
    ("refunds", "SELECT r.id FROM refunds r JOIN payments p ON p.id=r.payment_id WHERE p.ticket_id=ANY(:ids)"),
    ("logistics_records", "SELECT id FROM logistics_records WHERE ticket_id=ANY(:ids)"),
    ("warranty_claims", "SELECT id FROM warranty_claims WHERE ticket_id=ANY(:ids)"),
    ("ticket_audit_events", "SELECT id FROM ticket_audit_events WHERE ticket_id=ANY(:ids)"),
    ("warranties", "SELECT id FROM warranties WHERE ticket_id=ANY(:ids)"),
    ("payments", "SELECT id FROM payments WHERE ticket_id=ANY(:ids)"),
    ("quote_details", "SELECT d.id FROM quote_details d JOIN quotes q ON q.id=d.quote_id WHERE q.ticket_id=ANY(:ids)"),
    ("quotes", "SELECT id FROM quotes WHERE ticket_id=ANY(:ids)"),
    ("tickets", "SELECT id FROM tickets WHERE id=ANY(:ids)"),
)


def _positive_ids(values: Any, label: str, *, expected_count: int | None = None) -> list[int]:
    if not isinstance(values, list) or any(type(value) is not int or value < 1 for value in values):
        raise ValueError(f"El manifiesto tiene IDs inválidos en {label}.")
    if len(values) != len(set(values)):
        raise ValueError(f"El manifiesto repite IDs en {label}.")
    if expected_count is not None and len(values) != expected_count:
        raise ValueError(f"El manifiesto debe incluir exactamente {expected_count} IDs en {label}.")
    return sorted(values)


def load_manifest(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("database") != "multiagentedb" or data.get("snapshot_date") != "2026-11-03":
        raise ValueError("El manifiesto no corresponde al snapshot local autorizado.")
    data["tickets"] = _positive_ids(data.get("tickets"), "tickets", expected_count=8)
    children = data.get("children")
    if not isinstance(children, dict) or set(children) != set(DEPENDENCY_QUERIES) | {"quote_details"}:
        raise ValueError("El manifiesto de dependencias está incompleto o contiene tablas no aprobadas.")
    for table, values in children.items():
        children[table] = _positive_ids(values, table)
    return data


def _column_ids(connection, statement: str, ids: list[int]) -> list[int]:
    return sorted(connection.execute(text(statement), {"ids": ids}).scalars().all())


def preflight(connection, manifest: dict[str, Any], *, lock_tickets: bool = False) -> dict[str, list[int]]:
    database = connection.execute(text("SELECT current_database()")).scalar_one()
    if database != manifest["database"]:
        raise RuntimeError("La base conectada no coincide con el manifiesto.")
    ticket_query = "SELECT id FROM tickets WHERE id=ANY(:ids) AND request_type::text='SALE' ORDER BY id"
    if lock_tickets:
        ticket_query += " FOR UPDATE"
    tickets = _column_ids(connection, ticket_query, manifest["tickets"])
    if tickets != manifest["tickets"]:
        raise RuntimeError("Los tickets SALE actuales no coinciden exactamente con los ocho IDs aprobados.")
    actual = {}
    for table, statement in DEPENDENCY_QUERIES.items():
        actual[table] = _column_ids(connection, statement, manifest["tickets"])
    actual["quote_details"] = _column_ids(connection,
        "SELECT d.id FROM quote_details d JOIN quotes q ON q.id=d.quote_id WHERE q.ticket_id=ANY(:ids) ORDER BY d.id",
        manifest["tickets"])
    for table, expected in manifest["children"].items():
        if actual[table] != expected:
            raise RuntimeError(f"La dependencia {table} cambió frente al manifiesto; no se borró nada.")
    quote_ids = manifest["children"]["quotes"]
    quote_dependent_relations = (
        ("sales_orders", "quote_id"),
        ("inventory_reservations", "quote_id"),
        ("inventory_reservation_items", "quote_detail_id"),
        ("quote_audit_events", "quote_id"),
    )
    for table, column in quote_dependent_relations:
        exists = connection.execute(text("SELECT to_regclass(:relation) IS NOT NULL"),
                                    {"relation": f"public.{table}"}).scalar_one()
        if exists and quote_ids:
            if column == "quote_detail_id":
                statement = f"SELECT id FROM public.{table} WHERE quote_detail_id IN (SELECT id FROM public.quote_details WHERE quote_id=ANY(:ids)) ORDER BY id"
            else:
                statement = f"SELECT id FROM public.{table} WHERE {column}=ANY(:ids) ORDER BY id"
            child_ids = _column_ids(connection, statement, quote_ids)
            if child_ids:
                raise RuntimeError(
                    f"Se encontraron registros en {table} asociados a la venta de prueba; "
                    "no están en el manifiesto aprobado, no se borró nada."
                )
    return actual


def execute_cleanup(connection, ticket_ids: list[int]) -> dict[str, int]:
    deleted: dict[str, int] = {}
    for table, select_ids in DELETE_ORDER:
        ids = connection.execute(text(select_ids), {"ids": ticket_ids}).scalars().all()
        if not ids:
            deleted[table] = 0
            continue
        result = connection.execute(text(f"DELETE FROM {table} WHERE id=ANY(:row_ids)"), {"row_ids": ids})
        if result.rowcount != len(ids):
            raise RuntimeError(f"El borrado de {table} afectó un recuento distinto al preflight.")
        deleted[table] = result.rowcount
    return deleted


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--execute", action="store_true", help="Ejecuta el borrado tras preflight estricto.")
    parser.add_argument("--confirm-database", help="Debe coincidir literalmente con el nombre aprobado.")
    parser.add_argument("--backup", type=Path, help="Archivo de respaldo existente y restaurable.")
    args = parser.parse_args()
    try:
        manifest = load_manifest(args.manifest)
        database_url = os.environ.get("CUSTOMER_COMMERCE_CLEANUP_DATABASE_URL", "").strip()
        approved_database = os.environ.get("CUSTOMER_COMMERCE_CLEANUP_APPROVED_DATABASE", "").strip()
        if not database_url or approved_database != manifest["database"]:
            raise RuntimeError("Configura la URL de limpieza y permite explícitamente la base indicada.")
        if args.execute:
            if args.confirm_database != manifest["database"]:
                raise RuntimeError("Usa --confirm-database con el nombre exacto del destino.")
            if not args.backup or not args.backup.is_file() or args.backup.stat().st_size == 0:
                raise RuntimeError("La ejecución exige indicar un archivo de respaldo existente y no vacío.")
        engine = create_engine(database_url, pool_pre_ping=True)
        try:
            with engine.begin() if args.execute else engine.connect() as connection:
                actual = preflight(connection, manifest, lock_tickets=args.execute)
                print(f"Preflight correcto: {len(manifest['tickets'])} tickets y dependencias coinciden; base={manifest['database']}.")
                if not args.execute:
                    print("Modo de solo lectura. No se eliminó ninguna fila.")
                    return 0
                deleted = execute_cleanup(connection, manifest["tickets"])
                print("Filas eliminadas por tabla: " + json.dumps(deleted, sort_keys=True))
                print(f"Respaldo declarado: {args.backup.name}")
        finally:
            engine.dispose()
        return 0
    except Exception as exc:
        print(f"Cleanup abortado: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
