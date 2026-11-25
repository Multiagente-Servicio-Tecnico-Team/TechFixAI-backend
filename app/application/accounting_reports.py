"""Orquestación y validación de consultas contables."""
from app.domain.accounting import AccountingValidationError


class AccountingReportsService:
    REPORTS = {"journal", "ledger", "trial_balance"}

    def __init__(self, repository):
        self.repository = repository

    def get_report(self, report_type, *, from_date, to_date, limit=50, offset=0, **filters):
        if report_type not in self.REPORTS:
            raise AccountingValidationError("El tipo de reporte no es válido.")
        if from_date > to_date:
            raise AccountingValidationError("El rango de fechas no es válido.")
        if not 1 <= limit <= 10000 or offset < 0:
            raise AccountingValidationError("La paginación del reporte no es válida.")
        return self.repository.accounting_report(report_type, from_date=from_date, to_date=to_date,
                                                limit=limit, offset=offset, **filters)
