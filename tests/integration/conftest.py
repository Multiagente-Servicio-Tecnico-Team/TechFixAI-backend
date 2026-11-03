"""Fixtures PostgreSQL explícitas para las integraciones contables.

Nunca toma DATABASE_URL ni carga .env: la variable debe apuntar a una BD de prueba.
"""
import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url


@pytest.fixture
def accounting_test_engine():
    configured_url = os.environ.get("ACCOUNTING_TEST_DATABASE_URL", "").strip()
    if not configured_url:
        pytest.skip("Define ACCOUNTING_TEST_DATABASE_URL para pruebas PostgreSQL contables.")
    url = make_url(configured_url)
    if url.drivername in {"postgres", "postgresql"}:
        url = url.set(drivername="postgresql+pg8000")
    if not url.drivername.startswith("postgresql"):
        pytest.fail("ACCOUNTING_TEST_DATABASE_URL debe apuntar a PostgreSQL.")
    engine = create_engine(url, pool_pre_ping=True)
    try:
        yield engine
    finally:
        engine.dispose()
