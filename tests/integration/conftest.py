"""Explicit PostgreSQL fixtures for integration tests.

Never load DATABASE_URL or the developer .env. Test database URLs are passed
through dedicated environment variables. Purchase-order tests additionally
require a disposable database name containing "test".
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


@pytest.fixture
def purchase_order_test_engine():
    configured_url = os.environ.get("PURCHASE_ORDER_TEST_DATABASE_URL", "").strip()
    if not configured_url:
        pytest.skip("Define PURCHASE_ORDER_TEST_DATABASE_URL para las pruebas de órdenes.")
    url = make_url(configured_url)
    if url.drivername in {"postgres", "postgresql"}:
        url = url.set(drivername="postgresql+pg8000")
    if not url.drivername.startswith("postgresql"):
        pytest.fail("PURCHASE_ORDER_TEST_DATABASE_URL debe apuntar a PostgreSQL.")
    if "test" not in (url.database or "").lower():
        pytest.fail("La base de pruebas de órdenes debe ser desechable y tener 'test' en su nombre.")
    engine = create_engine(url, pool_pre_ping=True)
    try:
        yield engine
    finally:
        engine.dispose()
