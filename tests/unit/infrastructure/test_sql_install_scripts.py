"""Contrato estático de los scripts de instalación de la base (sql/README.md)."""
import re
from pathlib import Path

from app.domain.inventory import CODE_PATTERN

SQL = Path(__file__).resolve().parents[3] / "sql"
SCHEMA = SQL / "esquema-vacio-produccion.sql"
SEED = SQL / "seeds" / "datos-iniciales.sql"
BCRYPT = re.compile(r"\$2[aby]\$\d{2}\$[./A-Za-z0-9]{53}")


def _statements(text: str) -> list[str]:
    return [line for line in text.splitlines() if line.strip() and not line.lstrip().startswith("--")]


def test_schema_runs_in_one_transaction_on_postgres_16_and_17():
    lines = _statements(SCHEMA.read_text(encoding="utf-8"))
    assert lines[0].strip() == "BEGIN;"
    assert lines[-1].strip() == "COMMIT;"
    text = "\n".join(lines)
    assert "transaction_timeout" not in text
    assert "CREATE SCHEMA IF NOT EXISTS public;" in text
    assert not re.search(r"^CREATE SCHEMA public;", text, re.M)


def test_schema_constraints_have_balanced_parentheses():
    # Un paréntesis de más en un CHECK hace fallar toda la instalación.
    for number, line in enumerate(SCHEMA.read_text(encoding="utf-8").splitlines(), 1):
        if "CONSTRAINT" in line and "CHECK" in line:
            assert line.count("(") == line.count(")"), f"línea {number} desbalanceada"


def test_seed_never_stores_the_admin_password():
    seed = SEED.read_text(encoding="utf-8")
    assert not BCRYPT.search(seed), "el seed no debe traer un hash de contraseña"
    assert "current_setting('techfix.admin_password_hash', true)" in seed
    assert "RAISE EXCEPTION 'Falta el hash bcrypt" in seed
    assert "'ADMIN'" in seed


def test_seed_loads_inventory_with_opening_balances_and_pcge_in_one_transaction():
    seed = SEED.read_text(encoding="utf-8")
    lines = _statements(seed)
    assert lines[0].strip() == "BEGIN;" and lines[-1].strip() == "COMMIT;"
    assert sum(1 for line in lines if line.strip() in ("BEGIN;", "COMMIT;")) == 2
    codes = re.findall(r"^\('([^']+)',", seed, re.M)
    assert len(codes) == 433
    assert len(set(codes)) == len(codes), "códigos de repuesto repetidos"
    # El backend solo acepta estos SKU al editar (PUT /api/inventory/parts/{code}).
    assert [code for code in codes if not CODE_PATTERN.fullmatch(code)] == []
    assert seed.count("ON CONFLICT (code) DO NOTHING") == 2
    assert "'OPENING_BALANCE'" in seed and "'SYSTEM'" in seed
    assert "IF (SELECT count(*) FROM _pcge_seed)<>1192" in seed
