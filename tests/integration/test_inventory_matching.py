"""Consulta real del repositorio sobre SQLite temporal en memoria, sin configuración."""
import ast
from decimal import Decimal
from pathlib import Path
import re
import unicodedata

import pytest
from sqlalchemy import MetaData, Table, create_engine, inspect, select, text
from sqlalchemy.engine import Connection, Engine


@pytest.fixture
def inventory():
    source = Path(__file__).resolve().parents[2] / "app/database/repository.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    namespace = dict(Decimal=Decimal, re=re, unicodedata=unicodedata,
                     MetaData=MetaData, Table=Table, inspect=inspect, select=select, Engine=Engine, Connection=Connection)
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef)
             and n.name in {"_table", "_column", "_normalize", "lookup_inventory"}]
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), "exec"), namespace)
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE spare_parts (id INTEGER PRIMARY KEY, name TEXT, current_stock INTEGER, unit_price NUMERIC, active BOOLEAN)"))
        connection.execute(text("INSERT INTO spare_parts VALUES (1, 'Disco Sólido SSD 500GB NVMe', 10, 180, 1)"))
    yield namespace["lookup_inventory"], engine
    engine.dispose()


@pytest.mark.parametrize("name", ["ssd 5000gb nvme", "ssd 500gb sata"])
def test_no_sustituye_capacidad_o_interfaz(inventory, name):
    lookup, engine = inventory
    result = lookup(name, 1, engine)
    assert result["found"] is False and result["available"] is False
    assert result["inventory_id"] is None and result["name"] == name


@pytest.mark.parametrize("name", ["ssd 500gb nvme", "SSD 500 GB NVMe"])
def test_coincidencia_normalizada_conserva_stock_y_precio(inventory, name):
    lookup, engine = inventory
    result = lookup(name, 1, engine)
    assert result["found"] is True
    assert result["stock"] == 10 and result["unit_price"] == Decimal("180")


def test_consulta_ambigua_no_elige_primera_fila(inventory):
    lookup, engine = inventory
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO spare_parts VALUES (2, 'SSD 500GB NVMe marca B', 10, 180, 1)"))
    result = lookup("ssd 500gb nvme", 1, engine)
    assert result["found"] is False and result["match_status"] == "ambiguous"
