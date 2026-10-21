from decimal import Decimal

from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from app.database.repository import lookup_inventory


def test_lookup_inventory_stock_actual():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    with engine.begin() as connection:
        connection.execute(text("""
            CREATE TABLE repuestos (
                id INTEGER PRIMARY KEY,
                nombre TEXT,
                precio_unitario NUMERIC,
                stock_actual INTEGER,
                activo BOOLEAN
            )
        """))

        connection.execute(text("""
            INSERT INTO repuestos
            (id, nombre, precio_unitario, stock_actual, activo)
            VALUES (2, 'Memoria RAM 16GB DDR4', 150, 2, 1)
        """))

    resultado = lookup_inventory(
        requested_name="Memoria RAM 16GB DDR4",
        quantity=1,
        engine=engine,
    )

    assert resultado["inventory_id"] == 2
    assert resultado["stock"] == 2
    assert resultado["unit_price"] == Decimal("150")
    assert resultado["available"] is True