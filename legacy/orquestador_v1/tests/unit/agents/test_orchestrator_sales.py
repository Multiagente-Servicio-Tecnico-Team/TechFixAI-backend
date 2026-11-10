from decimal import Decimal
from unittest.mock import Mock

import pytest

from app.agents.orquestador.agentes import ventas


@pytest.fixture
def quote_state():
    return {
        "user_id": 41,
        "ticket_id": 31,
        "ticket_code": "TCK-31",
        "ticket_status": "IN_DIAGNOSIS",
        "product": "Laptop",
        "category": "Soporte técnico",
        "symptoms": "No inicia",
        "diagnosis": "Revisión requerida",
        "labor_task_type": "maintenance",
        "labor_cost": Decimal("35.00"),
        "available_parts": [{
            "code": "SSD-512",
            "name": "SSD NVMe 512GB",
            "quantity": 1,
            "unit_price": Decimal("44.90"),
            "stock": 4,
            "current_stock": 4,
            "available": True,
        }],
        "parts_total": Decimal("44.90"),
        "total": Decimal("79.90"),
        "ticket_confirmed": True,
        "awaiting_ticket_confirmation": False,
    }


def test_orchestrator_reprices_before_persisting_if_catalog_price_changed(
    monkeypatch, quote_state
):
    repository = Mock()
    repository.find_by_code.return_value = {
        "id": 7, "code": "SSD-512", "name": "SSD NVMe 512GB",
        "category": "Almacenamiento", "unit_price": Decimal("49.90"),
        "current_stock": 4,
    }
    monkeypatch.setattr(ventas, "catalog_service", repository, raising=False)
    database = Mock()
    monkeypatch.setattr(ventas, "sales_repository", database, raising=False)

    result = ventas.persistencia_node(quote_state)

    database.accept_ticket_quote.assert_not_called()
    assert result["awaiting_ticket_confirmation"] is True
    assert result["ticket_confirmed"] is False
    assert result["total"] == Decimal("84.90")
    assert "cambi" in result["response"].casefold()


def test_orchestrator_never_persists_a_quote_after_stock_becomes_insufficient(
    monkeypatch, quote_state
):
    repository = Mock()
    repository.find_by_code.return_value = {
        "id": 7, "code": "SSD-512", "name": "SSD NVMe 512GB",
        "category": "Almacenamiento", "unit_price": Decimal("44.90"),
        "current_stock": 0,
    }
    monkeypatch.setattr(ventas, "catalog_service", repository, raising=False)
    database = Mock()
    monkeypatch.setattr(ventas, "sales_repository", database, raising=False)

    result = ventas.persistencia_node(quote_state)

    database.accept_ticket_quote.assert_not_called()
    assert result["awaiting_ticket_confirmation"] is False
    assert "stock" in result["response"].casefold()


def test_orchestrator_persists_after_current_catalog_values_match(
    monkeypatch, quote_state
):
    repository = Mock()
    repository.find_by_code.return_value = {
        "id": 7, "code": "SSD-512", "name": "SSD NVMe 512GB",
        "category": "Almacenamiento", "unit_price": Decimal("44.90"),
        "current_stock": 4,
    }
    monkeypatch.setattr(ventas, "catalog_service", repository, raising=False)
    database = Mock()
    database.accept_ticket_quote.return_value = {
        "quote_id": 91, "payment_id": 92,
        "payment_code": "PAY-81", "payment_status": "PENDING",
    }
    monkeypatch.setattr(ventas, "sales_repository", database, raising=False)

    result = ventas.persistencia_node(quote_state)

    database.accept_ticket_quote.assert_called_once()
    assert result["quote_id"] == 91
    assert result["ticket_code"] == "TCK-31"


def test_orchestrator_acceptance_uses_existing_ticket_and_leaves_payment_pending(
    monkeypatch, quote_state
):
    catalog = Mock()
    catalog.find_by_code.return_value = {
        "id": 7, "code": "SSD-512", "name": "SSD NVMe 512GB",
        "category": "Almacenamiento", "unit_price": Decimal("44.90"),
        "current_stock": 4,
    }
    monkeypatch.setattr(ventas, "catalog_service", catalog)
    legacy_writer = Mock()
    monkeypatch.setattr(ventas, "create_ticket_with_quote", legacy_writer, raising=False)
    database = Mock()
    database.accept_ticket_quote.return_value = {
        "quote_id": 91, "payment_id": 92,
        "payment_code": "PAY-91", "payment_status": "PENDING",
    }
    monkeypatch.setattr(ventas, "sales_repository", database, raising=False)

    result = ventas.persistencia_node(quote_state)

    legacy_writer.assert_not_called()
    database.accept_ticket_quote.assert_called_once()
    assert result["quote_id"] == 91
    assert result["payment_code"] == "PAY-91"
    assert result["ticket_id"] == 31
    assert result["ticket_code"] == "TCK-31"
    assert result["ticket_status"] == "PAYMENT_PENDING"
