from datetime import date
from decimal import Decimal

import pytest

from app.domain.accounting import AccountingValidationError, EntryLine, EntryDraft, reverse_lines, validate_draft


def valid_draft(**overrides):
    values = {
        "operation_date": date(2026, 11, 2),
        "concept": "Servicio técnico",
        "detail": "Diagnóstico y reparación",
        "category_id": 1,
        "lines": (
            EntryLine("621", "Gastos", None, Decimal("100.00"), Decimal("0.00")),
            EntryLine("104", "Caja", "Pago recibido", Decimal("0.00"), Decimal("100.00")),
        ),
    }
    values.update(overrides)
    return EntryDraft(**values)


def test_balanced_decimal_entry_is_accepted():
    result = validate_draft(valid_draft())
    assert result.debit_total == result.credit_total == Decimal("100.00")
    assert result.currency == "PEN"


@pytest.mark.parametrize(
    "draft",
    [
        valid_draft(lines=()),
        valid_draft(lines=tuple([EntryLine("1", "Cuenta", None, Decimal("1.00"), Decimal("0"))] * 101)),
        valid_draft(lines=(EntryLine("1", "Cuenta", None, Decimal("1.00"), Decimal("1.00")), EntryLine("2", "Cuenta", None, Decimal("0"), Decimal("1.00")))),
        valid_draft(concept=""),
    ],
)
def test_invalid_entries_are_rejected(draft):
    with pytest.raises(AccountingValidationError):
        validate_draft(draft)


def test_unbalanced_entry_is_rejected():
    with pytest.raises(AccountingValidationError, match="balance"):
        validate_draft(valid_draft(lines=(
            EntryLine("1", "Cuenta", None, Decimal("10.00"), Decimal("0.00")),
            EntryLine("2", "Cuenta", None, Decimal("0.00"), Decimal("9.99")),
        )))


@pytest.mark.parametrize(
    "draft",
    [
        valid_draft(lines=(
            EntryLine("1" * 41, "Debe", None, Decimal("2.00"), Decimal("0.00")),
            EntryLine("2", "Haber", None, Decimal("0.00"), Decimal("2.00")),
        )),
        valid_draft(lines=(
            EntryLine("1", "D" * 201, None, Decimal("2.00"), Decimal("0.00")),
            EntryLine("2", "Haber", None, Decimal("0.00"), Decimal("2.00")),
        )),
        valid_draft(lines=(
            EntryLine("1", "Debe", "x" * 1001, Decimal("2.00"), Decimal("0.00")),
            EntryLine("2", "Haber", None, Decimal("0.00"), Decimal("2.00")),
        )),
        valid_draft(detail="d" * 4001),
        valid_draft(concept="c" * 201),
        valid_draft(lines=(
            EntryLine("1", "Debe", None, Decimal("1000000000000.00"), Decimal("0.00")),
            EntryLine("2", "Haber", None, Decimal("0.00"), Decimal("1000000000000.00")),
        )),
    ],
)
def test_field_limits_and_numeric_precision_are_enforced(draft):
    with pytest.raises(AccountingValidationError):
        validate_draft(draft)


def test_reverse_lines_swaps_debit_and_credit():
    reversed_lines = reverse_lines(valid_draft().lines)
    assert reversed_lines[0].debit == Decimal("0.00")
    assert reversed_lines[0].credit == Decimal("100.00")
    assert reversed_lines[1].debit == Decimal("100.00")
