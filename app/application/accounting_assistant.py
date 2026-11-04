"""Validación temporal de datos contables ingresados manualmente por ADMIN."""
from datetime import date
from decimal import Decimal, InvalidOperation
import re
import unicodedata

from app.domain.accounting import AccountingValidationError, EntryDraft, EntryLine, validate_draft


REQUIRED = ("operation_date", "concept", "detail", "category_id", "lines")
LINE_REQUIRED = ("account_code", "account_name", "debit", "credit")
MONEY_PATTERN = re.compile(r"^(0|[1-9][0-9]{0,11})\.[0-9]{2}$")


def accounting_intent(message: str) -> bool:
    """Reconoce una solicitud contable; no interpreta datos de negocio."""
    normalized = "".join(char for char in unicodedata.normalize("NFD", message.casefold())
                         if unicodedata.category(char) != "Mn")
    return bool(re.search(r"\b(asientos?|contabilidad|contables?|contador|reversion)\b", normalized))


class AccountingAssistant:
    """Lecturas de 003 y preparación de reversión, sin escritura desde el chat."""

    def __init__(self, service, *, authenticated_role: str):
        if authenticated_role != "ADMIN":
            raise PermissionError("Esta operación requiere una sesión ADMIN.")
        self.service = service

    def list_categories(self):
        return self.service.list_categories()

    def list_entries(self, **filters):
        allowed = {"from_date", "to_date", "category_id", "status", "entry_number", "limit", "offset"}
        if set(filters) - allowed:
            raise AccountingValidationError("Filtro contable no admitido.")
        if filters.get("status") not in (None, "CONFIRMED", "REVERSED"):
            raise AccountingValidationError("Estado contable no admitido.")
        for field in ("category_id", "entry_number", "limit", "offset"):
            value = filters.get(field)
            if value is not None and (type(value) is not int or value < (0 if field == "offset" else 1)):
                raise AccountingValidationError(f"El filtro {field} no es válido.")
        if filters.get("limit", 50) > 100:
            raise AccountingValidationError("El límite máximo es 100.")
        for field in ("from_date", "to_date"):
            if filters.get(field) is not None and not isinstance(filters[field], date):
                raise AccountingValidationError(f"El filtro {field} no es válido.")
        if filters.get("from_date") and filters.get("to_date") and filters["from_date"] > filters["to_date"]:
            raise AccountingValidationError("El rango de fechas no es válido.")
        return self.service.list_entries(**{**{"from_date": None, "to_date": None, "category_id": None,
                                              "status": None, "entry_number": None, "limit": 50, "offset": 0}, **filters})

    def get_entry(self, entry_id: int):
        if type(entry_id) is not int or entry_id < 1:
            raise AccountingValidationError("El identificador no es válido.")
        return self.service.get_entry(entry_id)

    def prepare_reversal(self, *, entry_id: int, operation_date: date, reason: str):
        """Comprueba los datos y el original; la reversión exige el POST de 003."""
        if not isinstance(operation_date, date):
            raise AccountingValidationError("La fecha de reversión no es válida.")
        if not isinstance(reason, str) or not 1 <= len(reason.strip()) <= 2000:
            raise AccountingValidationError("La razón debe tener entre 1 y 2000 caracteres.")
        self.get_entry(entry_id)
        return {"entry_id": entry_id, "operation_date": operation_date.isoformat(), "reason": reason.strip()}


def prepare_manual_entry(data: dict) -> dict:
    """Devuelve un payload validado para 003; no lee ni escribe asientos."""
    if not isinstance(data, dict):
        raise AccountingValidationError("Proporciona los datos contables como un objeto.")
    if set(data) - set(REQUIRED):
        raise AccountingValidationError("Hay campos contables no admitidos por 003.")
    missing = [field for field in REQUIRED if field not in data]
    if missing:
        raise AccountingValidationError("Faltan datos: " + ", ".join(missing) + ".")
    if not isinstance(data["lines"], list):
        raise AccountingValidationError("Las líneas deben ser una lista.")
    lines = []
    for index, item in enumerate(data["lines"], start=1):
        if not isinstance(item, dict):
            raise AccountingValidationError(f"La línea {index} no es válida.")
        if set(item) - {*LINE_REQUIRED, "description"}:
            raise AccountingValidationError(f"La línea {index} contiene campos no admitidos.")
        missing = [field for field in LINE_REQUIRED if field not in item]
        if missing:
            raise AccountingValidationError(f"Faltan datos de línea {index}: " + ", ".join(missing) + ".")
        if not all(isinstance(item[field], str) and MONEY_PATTERN.fullmatch(item[field])
                   for field in ("debit", "credit")):
            raise AccountingValidationError(f"Los importes de línea {index} requieren dos decimales.")
        try:
            debit = Decimal(str(item["debit"]))
            credit = Decimal(str(item["credit"]))
        except (InvalidOperation, TypeError, ValueError):
            raise AccountingValidationError(f"Los importes de línea {index} no son decimales válidos.") from None
        if not isinstance(item["account_code"], str) or not isinstance(item["account_name"], str):
            raise AccountingValidationError(f"La cuenta de línea {index} no es válida.")
        description = item.get("description")
        if description is not None and not isinstance(description, str):
            raise AccountingValidationError(f"La descripción de línea {index} no es válida.")
        lines.append(EntryLine(item["account_code"], item["account_name"], description, debit, credit))
    try:
        operation_date = date.fromisoformat(data["operation_date"])
    except (TypeError, ValueError):
        raise AccountingValidationError("La fecha de operación no es válida.") from None
    if not isinstance(data["concept"], str) or not isinstance(data["detail"], str):
        raise AccountingValidationError("Concepto y detalle deben ser textos.")
    if type(data["category_id"]) is not int:
        raise AccountingValidationError("La categoría no es válida.")
    draft = EntryDraft(operation_date, data["concept"], data["detail"], data["category_id"], tuple(lines))
    validated = validate_draft(draft)
    return {
        "operation_date": draft.operation_date.isoformat(),
        "concept": draft.concept,
        "detail": draft.detail,
        "category_id": draft.category_id,
        "lines": [{
            "account_code": line.account_code,
            "account_name": line.account_name,
            "description": line.description,
            "debit": format(line.debit, ".2f"),
            "credit": format(line.credit, ".2f"),
        } for line in draft.lines],
        "debit_total": format(validated.debit_total, ".2f"),
        "credit_total": format(validated.credit_total, ".2f"),
        "currency": validated.currency,
    }
