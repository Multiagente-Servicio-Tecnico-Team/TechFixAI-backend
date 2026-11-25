"""Exportación determinista del Libro Diario electrónico SUNAT (PLE 5.1)."""
import os
import re
from datetime import date
from decimal import Decimal


def _filename(ruc: str, year: int, month: int, has_movements: bool) -> str:
    indicator = "1" if has_movements else "0"
    return f"LE{ruc}{year:04d}{month:02d}0005010000{indicator}{indicator}11.txt"


def _safe(value) -> str:
    return re.sub(r"[|\r\n]+", " ", str(value or "")).strip()


def build_libro_diario(rows, year: int, month: int, ruc: str | None = None) -> dict:
    ruc = ruc if ruc is not None else os.getenv("COMPANY_RUC", "20601234567")
    errors = []
    if month < 1 or month > 12 or year < 2000 or year > 9999:
        errors.append("El periodo debe tener un año entre 2000 y 9999 y un mes entre 01 y 12.")
    if not re.fullmatch(r"\d{11}", ruc or ""):
        errors.append("COMPANY_RUC debe contener exactamente 11 dígitos.")
    entries = {}
    entry_sequences = {}
    total_debit = Decimal("0.00")
    total_credit = Decimal("0.00")
    lines = []
    for row in rows:
        entry_id = str(row["id"])
        entries[entry_id] = None
        entry_sequences[entry_id] = entry_sequences.get(entry_id, 0) + 1
        debit = Decimal(str(row["debit"] or 0)).quantize(Decimal("0.01"))
        credit = Decimal(str(row["credit"] or 0)).quantize(Decimal("0.01"))
        total_debit += debit
        total_credit += credit
        if (debit > 0 and credit > 0) or (debit == 0 and credit == 0):
            errors.append(f"Asiento {entry_id}, línea {row['line_number']}: debe tener Debe o Haber positivo, pero no ambos ni ninguno.")
        operation_date = row["operation_date"]
        if isinstance(operation_date, str):
            operation_date = date.fromisoformat(operation_date)
        if operation_date.year != year or operation_date.month != month:
            errors.append(f"El asiento {entry_id} no pertenece al periodo solicitado.")
        period = f"{year:04d}{month:02d}00"
        date_value = operation_date.strftime("%d/%m/%Y")
        description = _safe(row.get("description"))[:200]
        account_code = _safe(row.get("account_code"))
        if not account_code:
            errors.append(f"Asiento {entry_id}, línea {row['line_number']}: falta el código de cuenta PCGE.")
        values = [period, entry_id[:40], f"M{entry_sequences[entry_id]:04d}", _safe(row["account_code"]),
                  "", "", "PEN", "", "", "00", "-", "0", date_value, "", date_value,
                  description, "", format(debit, ".2f"), format(credit, ".2f"), "", "1"]
        lines.append("|".join(values) + "|")
    if total_debit != total_credit:
        errors.append(f"El total Debe ({total_debit:.2f}) no coincide con el total Haber ({total_credit:.2f}).")
    filename = _filename(ruc or "", year, month, bool(lines))
    return {"valid": not errors, "filename": filename, "entries_count": len(entries),
            "lines_count": len(lines), "total_debit": format(total_debit, ".2f"),
            "total_credit": format(total_credit, ".2f"), "errors": errors,
            "content": "\r\n".join(lines) + ("\r\n" if lines else "")}


def validate_and_export_libro_diario(repository, year: int, month: int) -> dict:
    result = build_libro_diario(repository.ple_libro_diario(year, month), year, month)
    return result
