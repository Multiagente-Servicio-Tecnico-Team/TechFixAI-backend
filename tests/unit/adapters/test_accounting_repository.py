from datetime import date
from decimal import Decimal
from datetime import datetime, timezone

from app.adapters.persistence.accounting import AccountingRepositoryAdapter, _default_session_factory, money_string


def test_money_and_dates_are_serialized_without_float_rounding():
    assert money_string(Decimal("10.20")) == "10.20"
    assert date(2026, 11, 2).isoformat() == "2026-11-02"


def test_postgres_summary_row_is_converted_to_safe_api_values():
    row = {
        "id": 7, "entry_number": 123, "operation_date": date(2026, 11, 2), "concept": "Venta",
        "category_id": 1, "category_code": "SALE", "category_name": "Venta", "category_description": None,
        "currency": "PEN", "debit_total": Decimal("100.00"), "credit_total": Decimal("100.00"),
        "status": "CONFIRMED", "responsible_user_id": 8, "responsible_name": "Ana Admin ",
        "created_at": datetime(2026, 11, 2, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 11, 2, tzinfo=timezone.utc), "reversed_at": None,
        "reversal_of_entry_id": None, "reversal_entry_id": None,
        "accounting_plan_id": 3, "plan_code": "PCGE_PE", "plan_name": "PCGE Perú", "plan_edition": "Modificado 2019",
    }
    summary = AccountingRepositoryAdapter._summary_from_row(row)
    assert summary["entry_number"] == "123"
    assert summary["amount"] == "100.00"
    assert summary["responsible"]["display_name"] == "Ana Admin"
    assert summary["plan_id"] == 3
    assert summary["accounting_plan"] == {"id": 3, "code": "PCGE_PE", "name": "PCGE Perú", "edition": "Modificado 2019"}

    # Los asientos anteriores al catálogo contable no tienen plan.
    legacy = AccountingRepositoryAdapter._summary_from_row({**row, "accounting_plan_id": None, "plan_code": None, "plan_name": None, "plan_edition": None})
    assert legacy["plan_id"] is None and legacy["accounting_plan"] is None


def test_default_session_factory_uses_supported_sessionmaker_configuration(monkeypatch):
    from unittest.mock import Mock
    import app.database.connection as database

    session_factory = object()
    get_engine = Mock(return_value=object())
    monkeypatch.setattr(database, "SessionLocal", session_factory)
    monkeypatch.setattr(database, "get_engine", get_engine)

    assert _default_session_factory() is session_factory
    get_engine.assert_called_once_with()
