"""Inspección y registro explícito de migraciones PostgreSQL.

Esta utilidad nunca ejecuta archivos SQL. El operador ejecuta y valida el SQL
separadamente y solo entonces puede registrar la versión aplicada.
"""
from __future__ import annotations

import argparse
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import inspect, text

from app.database.connection import get_engine

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "sql" / "migrations"
_MIGRATION_NAME = re.compile(r"^(?P<version>\d{3})_[a-z0-9_]+\.sql$")


def _migration_checksum(contents: bytes) -> str:
    """Hash SQL independent of the checkout's CRLF/LF line-ending policy."""
    return hashlib.sha256(contents.replace(b"\r\n", b"\n")).hexdigest()


@dataclass(frozen=True)
class MigrationStatus:
    version: str
    filename: str
    checksum: str
    recorded_checksum: str | None
    applied_at: object | None

    @property
    def status(self) -> str:
        if self.recorded_checksum is None:
            return "UNRECORDED"
        if self.recorded_checksum != self.checksum:
            return "CHECKSUM_MISMATCH"
        return "RECORDED"


def _migration_files(directory: Path = MIGRATIONS_DIR) -> list[tuple[str, Path, str]]:
    files = []
    for path in sorted(directory.glob("*.sql")):
        match = _MIGRATION_NAME.fullmatch(path.name)
        if match:
            # Git may check out these SQL files with CRLF on Windows while the
            # ledger was created from LF bytes. Treat both representations as
            # the same migration so status remains stable across platforms.
            checksum = _migration_checksum(path.read_bytes())
            files.append((match.group("version"), path, checksum))
    versions = [version for version, _, _ in files]
    if len(versions) != len(set(versions)):
        raise ValueError("Hay más de una migración con la misma versión.")
    return files


def inspect_migrations(engine, directory: Path = MIGRATIONS_DIR) -> tuple[bool, list[MigrationStatus]]:
    """Return file/ledger state without writing to PostgreSQL."""
    inspector = inspect(engine)
    if not inspector.has_table("schema_migrations", schema="public"):
        return False, [
            MigrationStatus(version, path.name, checksum, None, None)
            for version, path, checksum in _migration_files(directory)
        ]

    with engine.connect() as connection:
        rows = connection.execute(
            text("SELECT version, checksum, applied_at FROM public.schema_migrations")
        ).mappings().all()
    recorded = {str(row["version"]): row for row in rows}
    result = []
    for version, path, checksum in _migration_files(directory):
        row = recorded.get(version)
        result.append(
            MigrationStatus(
                version=version,
                filename=path.name,
                checksum=checksum,
                recorded_checksum=str(row["checksum"]) if row else None,
                applied_at=row["applied_at"] if row else None,
            )
        )
    unknown = set(recorded) - {version for version, _, _ in _migration_files(directory)}
    for version in sorted(unknown):
        row = recorded[version]
        result.append(MigrationStatus(version, "<archivo ausente>", "", str(row["checksum"]), row["applied_at"]))
    return True, result


def record_verified_migration(engine, version: str, verified_by: str) -> None:
    """Record a migration after explicit operator verification; never apply SQL."""
    if not re.fullmatch(r"\d{3}", version):
        raise ValueError("La versión debe tener tres dígitos, por ejemplo 006.")
    if not verified_by.strip() or len(verified_by.strip()) > 120:
        raise ValueError("Indica el operador que verificó la migración.")
    file_map = {v: (path, checksum) for v, path, checksum in _migration_files()}
    if version not in file_map:
        raise ValueError(f"No se encontró el archivo SQL de la migración {version}.")
    path, checksum = file_map[version]
    with engine.begin() as connection:
        if not inspect(connection).has_table("schema_migrations", schema="public"):
            raise RuntimeError("El ledger schema_migrations no existe; primero aplica la migración que lo crea.")
        existing = connection.execute(
            text("SELECT checksum FROM public.schema_migrations WHERE version=:version FOR UPDATE"),
            {"version": version},
        ).scalar_one_or_none()
        if existing is not None:
            if existing != checksum:
                raise RuntimeError("El checksum registrado no coincide con el archivo actual; no se modifica el ledger.")
            return
        connection.execute(
            text("""INSERT INTO public.schema_migrations(version, filename, checksum, verified_by)
                    VALUES (:version, :filename, :checksum, :verified_by)"""),
            {"version": version, "filename": path.name, "checksum": checksum, "verified_by": verified_by.strip()},
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspecciona o registra migraciones ya aplicadas; no ejecuta SQL.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("status", help="Mostrar checksums y estado del ledger en modo solo lectura")
    record = subparsers.add_parser("record", help="Registrar una migración aplicada y verificada manualmente")
    record.add_argument("--version", required=True)
    record.add_argument("--verified-by", required=True)
    record.add_argument("--confirm-applied", action="store_true", help="Confirma que el SQL ya se aplicó y verificó")
    args = parser.parse_args()
    engine = get_engine()
    if args.command == "status":
        ledger_exists, statuses = inspect_migrations(engine)
        print("Ledger:", "presente" if ledger_exists else "ausente; requiere reconciliación manual")
        for item in statuses:
            print(item.version, item.filename, item.status, item.checksum)
        return 0
    if not args.confirm_applied:
        parser.error("No se registra nada sin --confirm-applied tras validar el esquema.")
    record_verified_migration(engine, args.version, args.verified_by)
    print(f"Migración {args.version} registrada tras verificación del operador.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
