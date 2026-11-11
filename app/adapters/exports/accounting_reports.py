"""Serialización de reportes contables a CSV y XLSX."""
import csv
from datetime import datetime, timezone
from io import BytesIO, StringIO


def _columns(report):
    if report["report"] == "journal":
        return ["operation_date", "entry_number", "entry_id", "concept", "account_code", "account_name",
                "account_id", "legacy_unlinked", "debit", "credit", "status", "reversal_of_entry_id"]
    if report["report"] == "ledger":
        return ["operation_date", "entry_number", "entry_id", "concept", "account_code", "account_name",
                "debit", "credit", "running_balance", "status"]
    return ["account_id", "account_code", "account_name", "legacy_unlinked", "normal_balance",
            "opening_debit", "opening_credit", "debit", "credit", "closing_debit", "closing_credit"]


def export_accounting_report(report, file_format):
    columns = _columns(report)
    generated = datetime.now(timezone.utc).isoformat()
    rows = report.get("items", [])
    if file_format == "csv":
        stream = StringIO(newline="")
        writer = csv.writer(stream)
        writer.writerow(["report", report["report"]])
        writer.writerow(["from_date", report["from_date"]])
        writer.writerow(["to_date", report["to_date"]])
        writer.writerow(["generated_at", generated])
        for key, value in report.get("filters", {}).items():
            writer.writerow([f"filter_{key}", value])
        writer.writerow(columns)
        for row in rows:
            writer.writerow([row.get(column, "") for column in columns])
        writer.writerow([])
        writer.writerow(["totals"])
        if report["report"] == "ledger":
            writer.writerow(["opening_balance", report.get("opening_balance", "")])
            writer.writerow(["closing_balance", report.get("closing_balance", "")])
        for key, value in report.get("totals", {}).items():
            writer.writerow([key, value])
        return stream.getvalue().encode("utf-8-sig"), "text/csv", "accounting-report.csv"
    if file_format != "xlsx":
        raise ValueError("Formato de exportación no admitido.")
    from openpyxl import Workbook
    output = BytesIO()
    workbook = Workbook(write_only=True)
    sheet = workbook.create_sheet("Reporte")
    sheet.append(["Reporte", report["report"]])
    sheet.append(["Desde", report["from_date"]])
    sheet.append(["Hasta", report["to_date"]])
    sheet.append(["Generado", generated])
    for key, value in report.get("filters", {}).items():
        sheet.append([f"Filtro {key}", value])
    sheet.append(columns)
    for row in rows:
        sheet.append([row.get(column) for column in columns])
    sheet.append([])
    sheet.append(["Totales"])
    if report["report"] == "ledger":
        sheet.append(["Saldo inicial", report.get("opening_balance", "")])
        sheet.append(["Saldo final", report.get("closing_balance", "")])
    for key, value in report.get("totals", {}).items():
        sheet.append([key, value])
    workbook.save(output)
    return output.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "accounting-report.xlsx"
