from datetime import date

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.adapters.api.accounting import create_accounting_router
from app.adapters.exports.ple_service import build_libro_diario


@pytest.fixture
def ple_rows():
    return [
        {
            "id": 41,
            "operation_date": date(2026, 11, 12),
            "line_number": 1,
            "account_code": "101",
            "description": "Venta",
            "debit": "118.00",
            "credit": "0.00",
        },
        {
            "id": 41,
            "operation_date": date(2026, 11, 12),
            "line_number": 2,
            "account_code": "701",
            "description": "Venta",
            "debit": "0.00",
            "credit": "118.00",
        },
    ]


def test_official_filename_has_expected_ruc_period_and_length(ple_rows):
    result = build_libro_diario(ple_rows, 2026, 11, ruc="20601234567")

    assert result["filename"] == "LE2060123456720261100050100001111.txt"
    assert len(result["filename"]) == 37


def test_each_line_has_21_columns_and_trailing_pipe(ple_rows):
    result = build_libro_diario(ple_rows, 2026, 11, ruc="20601234567")

    assert result["valid"] is True
    for line in result["content"].splitlines():
        assert line.count("|") == 21
        assert line.endswith("|")
        assert len(line.split("|")) - 1 == 21


def test_glosa_pipes_and_newlines_are_sanitized_without_changing_columns(ple_rows):
    ple_rows[0]["description"] = "Venta|mostrador\ncliente\r\nfinal"

    result = build_libro_diario(ple_rows, 2026, 11, ruc="20601234567")
    first_line = result["content"].splitlines()[0]

    assert "|mostrador" not in first_line
    assert "\n" not in first_line and "\r" not in first_line
    assert first_line.count("|") == 21
    assert first_line.endswith("|")
    assert "Venta mostrador cliente final" in first_line


def test_balanced_entry_passes_without_validation_errors(ple_rows):
    result = build_libro_diario(ple_rows, 2026, 11, ruc="20601234567")

    assert result["valid"] is True
    assert result["errors"] == []
    assert result["total_debit"] == "118.00"
    assert result["total_credit"] == "118.00"


def test_unbalanced_entry_and_invalid_ruc_return_validation_errors(ple_rows):
    ple_rows[1]["credit"] = "117.99"
    unbalanced = build_libro_diario(ple_rows, 2026, 11, ruc="20601234567")
    invalid_ruc = build_libro_diario(ple_rows, 2026, 11, ruc="1234")

    assert unbalanced["valid"] is False
    assert any("no coincide" in error for error in unbalanced["errors"])
    assert invalid_ruc["valid"] is False
    assert any("11 dígitos" in error for error in invalid_ruc["errors"])


def test_unbalanced_period_returns_http_422_on_export(ple_rows):
    ple_rows[1]["credit"] = "117.99"

    class FakeAccountingRepository:
        def ple_libro_diario(self, year, month):
            assert (year, month) == (2026, 11)
            return ple_rows

    class AdminUser:
        id = 1

    def require_admin():
        return AdminUser()

    app = FastAPI()
    app.include_router(create_accounting_router(lambda: FakeAccountingRepository(), require_admin))
    app.dependency_overrides[require_admin] = lambda: AdminUser()
    client = TestClient(app)

    response = client.get("/api/admin/accounting/ple/libro-diario/export?year=2026&month=11")

    assert response.status_code == 422
    assert response.json()["code"] == "ple_validation"
    assert any("no coincide" in error for error in response.json()["errors"])


def test_empty_period_uses_zero_movement_indicators():
    result = build_libro_diario([], 2026, 11, ruc="20601234567")

    assert result["valid"] is True
    assert result["entries_count"] == 0
    assert result["lines_count"] == 0
    assert result["filename"] == "LE2060123456720261100050100000011.txt"
    assert result["filename"].endswith("000011.txt")
    assert result["content"] == ""
