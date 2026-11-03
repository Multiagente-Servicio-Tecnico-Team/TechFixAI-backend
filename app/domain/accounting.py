"""Reglas puras para el libro contable interno en PEN."""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal


class AccountingValidationError(ValueError):
    """La operación contable no cumple las reglas del dominio."""


@dataclass(frozen=True)
class EntryLine:
    account_code: str
    account_name: str
    description: str | None
    debit: Decimal
    credit: Decimal


@dataclass(frozen=True)
class EntryDraft:
    operation_date: date
    concept: str
    detail: str
    category_id: int
    lines: tuple[EntryLine, ...]


@dataclass(frozen=True)
class ValidatedEntry:
    draft: EntryDraft
    debit_total: Decimal
    credit_total: Decimal
    currency: str = "PEN"


def _amount(value: Decimal, field: str) -> Decimal:
    if not isinstance(value, Decimal):
        raise AccountingValidationError(f"{field} debe ser un importe decimal.")
    if not value.is_finite() or value < 0 or value.as_tuple().exponent < -2:
        raise AccountingValidationError(f"{field} debe tener hasta dos decimales y no ser negativo.")
    if value.adjusted() > 11:
        raise AccountingValidationError(f"{field} excede la precisión NUMERIC(14,2).")
    return value.quantize(Decimal("0.01"))


def validate_draft(draft: EntryDraft) -> ValidatedEntry:
    if not isinstance(draft.operation_date, date):
        raise AccountingValidationError("La fecha de operación no es válida.")
    if not 1 <= len(draft.concept.strip()) <= 200:
        raise AccountingValidationError("El concepto debe tener entre 1 y 200 caracteres.")
    if not 1 <= len(draft.detail.strip()) <= 4000:
        raise AccountingValidationError("El detalle debe tener entre 1 y 4000 caracteres.")
    if not isinstance(draft.category_id, int) or draft.category_id < 1:
        raise AccountingValidationError("La categoría no es válida.")
    if not 2 <= len(draft.lines) <= 100:
        raise AccountingValidationError("El asiento debe contener entre 2 y 100 líneas.")

    debit_total = Decimal("0.00")
    credit_total = Decimal("0.00")
    for number, line in enumerate(draft.lines, start=1):
        if not 1 <= len(line.account_code.strip()) <= 40:
            raise AccountingValidationError(f"La línea {number} requiere un código de cuenta de 1 a 40 caracteres.")
        if not 1 <= len(line.account_name.strip()) <= 200:
            raise AccountingValidationError(f"La línea {number} requiere una denominación de 1 a 200 caracteres.")
        if line.description is not None and len(line.description) > 1000:
            raise AccountingValidationError(f"La descripción de la línea {number} supera 1000 caracteres.")
        debit = _amount(line.debit, f"Debe de línea {number}")
        credit = _amount(line.credit, f"Haber de línea {number}")
        if (debit > 0) == (credit > 0):
            raise AccountingValidationError(f"La línea {number} debe tener exactamente un importe positivo.")
        debit_total += debit
        credit_total += credit

    if debit_total <= 0 or debit_total != credit_total:
        raise AccountingValidationError("Los totales del debe y haber deben ser iguales y mayores que cero (balance).")
    if debit_total > Decimal("999999999999.99"):
        raise AccountingValidationError("El total excede la precisión NUMERIC(14,2).")
    return ValidatedEntry(draft, debit_total, credit_total)


def reverse_lines(lines: tuple[EntryLine, ...]) -> tuple[EntryLine, ...]:
    return tuple(EntryLine(line.account_code, line.account_name, line.description, line.credit, line.debit) for line in lines)
