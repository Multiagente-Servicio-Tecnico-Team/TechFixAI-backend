"""Reglas puras para el libro contable interno en PEN."""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Iterable


class AccountingValidationError(ValueError):
    """La operación contable no cumple las reglas del dominio."""


@dataclass(frozen=True)
class EntryLine:
    account_code: str
    account_name: str
    description: str | None
    debit: Decimal
    credit: Decimal
    account_id: int | None = None


@dataclass(frozen=True)
class EntryDraft:
    operation_date: date
    concept: str
    detail: str
    category_id: int
    lines: tuple[EntryLine, ...]
    accounting_plan_id: int | None = None


@dataclass(frozen=True)
class AccountingPlan:
    id: int | None
    code: str
    edition: str
    name: str
    jurisdiction: str
    status: str = "ACTIVE"
    is_default: bool = False


@dataclass(frozen=True)
class AccountingAccount:
    id: int | None
    plan_id: int
    code: str
    name: str
    parent_account_id: int | None
    normal_balance: str | None
    is_postable: bool
    status: str = "ACTIVE"
    effective_from: date | None = None
    effective_to: date | None = None


@dataclass(frozen=True)
class AccountingPeriod:
    year: int
    month: int
    status: str = "OPEN"


def validate_accounting_plan(plan: AccountingPlan) -> AccountingPlan:
    if not plan.code.strip() or len(plan.code.strip()) > 80:
        raise AccountingValidationError("El código del plan debe tener entre 1 y 80 caracteres.")
    if not plan.edition.strip() or len(plan.edition.strip()) > 80:
        raise AccountingValidationError("La edición del plan debe tener entre 1 y 80 caracteres.")
    if not plan.name.strip() or len(plan.name.strip()) > 200:
        raise AccountingValidationError("El nombre del plan debe tener entre 1 y 200 caracteres.")
    if not plan.jurisdiction.strip() or len(plan.jurisdiction.strip()) > 8:
        raise AccountingValidationError("La jurisdicción del plan no es válida.")
    if plan.status not in {"ACTIVE", "INACTIVE"}:
        raise AccountingValidationError("El estado del plan debe ser ACTIVE o INACTIVE.")
    return plan


def validate_accounting_account(account: AccountingAccount) -> AccountingAccount:
    if account.plan_id < 1 or not account.code.strip() or len(account.code.strip()) > 40:
        raise AccountingValidationError("El plan o código de cuenta no es válido.")
    if not account.name.strip() or len(account.name.strip()) > 200:
        raise AccountingValidationError("El nombre de cuenta debe tener entre 1 y 200 caracteres.")
    if account.status not in {"ACTIVE", "INACTIVE"}:
        raise AccountingValidationError("El estado de cuenta debe ser ACTIVE o INACTIVE.")
    if account.normal_balance not in {None, "DEBIT", "CREDIT"}:
        raise AccountingValidationError("El saldo normal debe ser DEBIT o CREDIT.")
    if account.effective_from and account.effective_to and account.effective_to < account.effective_from:
        raise AccountingValidationError("La fecha final de vigencia no puede preceder a la inicial.")
    if account.is_postable and account.normal_balance is None:
        raise AccountingValidationError("Una cuenta imputable requiere saldo normal DEBIT o CREDIT.")
    return account


def validate_account_hierarchy(accounts: Iterable[AccountingAccount]) -> None:
    rows = list(accounts)
    by_id = {account.id: account for account in rows if account.id is not None}
    by_plan_code = {(account.plan_id, account.code) for account in rows}
    if len(by_plan_code) != len(rows):
        raise AccountingValidationError("El código de cuenta debe ser único dentro del plan.")
    for account in rows:
        validate_accounting_account(account)
        if account.parent_account_id is None:
            continue
        parent = by_id.get(account.parent_account_id)
        if parent is None or parent.plan_id != account.plan_id:
            raise AccountingValidationError("La cuenta padre debe existir dentro del mismo plan.")
        if parent.is_postable:
            raise AccountingValidationError("Una cuenta con descendientes no puede ser imputable.")
        visited = {account.id}
        cursor = parent
        while cursor is not None:
            if cursor.id in visited:
                raise AccountingValidationError("La jerarquía de cuentas no puede contener ciclos.")
            visited.add(cursor.id)
            cursor = by_id.get(cursor.parent_account_id) if cursor.parent_account_id is not None else None


def validate_period(year: int, month: int, status: str = "OPEN") -> AccountingPeriod:
    if not 2000 <= year <= 9999 or not 1 <= month <= 12:
        raise AccountingValidationError("El periodo debe indicar un año y mes calendario válidos.")
    if status not in {"OPEN", "CLOSED"}:
        raise AccountingValidationError("El estado del periodo debe ser OPEN o CLOSED.")
    return AccountingPeriod(year, month, status)


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
    if draft.accounting_plan_id is not None and draft.accounting_plan_id < 1:
        raise AccountingValidationError("El plan contable no es válido.")
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
        if line.account_id is not None and line.account_id < 1:
            raise AccountingValidationError(f"La cuenta de la línea {number} no es válida.")
        debit_total += debit
        credit_total += credit

    if debit_total <= 0 or debit_total != credit_total:
        raise AccountingValidationError("Los totales del debe y haber deben ser iguales y mayores que cero (balance).")
    if debit_total > Decimal("999999999999.99"):
        raise AccountingValidationError("El total excede la precisión NUMERIC(14,2).")
    return ValidatedEntry(draft, debit_total, credit_total)


def reverse_lines(lines: tuple[EntryLine, ...]) -> tuple[EntryLine, ...]:
    return tuple(EntryLine(line.account_code, line.account_name, line.description, line.credit, line.debit, line.account_id) for line in lines)
