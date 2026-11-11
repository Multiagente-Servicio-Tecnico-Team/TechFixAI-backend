"""Helpers opt-in para tests PostgreSQL de customer-commerce.

No lee `.env` y no crea/modifica objetos en la base de desarrollo por defecto.
"""
from __future__ import annotations

import os

from sqlalchemy.engine import make_url


def customer_commerce_test_url() -> str:
    value = os.getenv("CUSTOMER_COMMERCE_TEST_DATABASE_URL", "").strip()
    if not value:
        raise RuntimeError("Define CUSTOMER_COMMERCE_TEST_DATABASE_URL a una base descartable.")
    url = make_url(value)
    if not url.drivername.startswith("postgresql"):
        raise RuntimeError("CUSTOMER_COMMERCE_TEST_DATABASE_URL debe apuntar a PostgreSQL.")
    if not url.database or "test" not in url.database.casefold():
        raise RuntimeError("El nombre de la base de prueba debe contener 'test'.")
    return value
