"""Casos de uso del catálogo de cuentas y periodos contables."""
from app.domain.accounting import (
    AccountingAccount,
    AccountingPlan,
    AccountingValidationError,
    validate_accounting_account,
    validate_accounting_plan,
    validate_period,
)


class AccountingCatalogService:
    def __init__(self, repository):
        self.repository = repository

    def list_plans(self):
        return self.repository.list_plans()

    def create_plan(self, actor_id, values):
        plan = AccountingPlan(None, values["code"], values["edition"], values["name"],
                              values["jurisdiction"], "ACTIVE", False)
        validate_accounting_plan(plan)
        if actor_id < 1:
            raise AccountingValidationError("El actor ADMIN no es válido.")
        return self.repository.create_plan(values | {"status": "ACTIVE", "is_default": False}, actor_id)

    def set_default_plan(self, plan_id, actor_id):
        if plan_id < 1 or actor_id < 1:
            raise AccountingValidationError("El plan o actor ADMIN no es válido.")
        return self.repository.set_default_plan(plan_id, actor_id)

    def list_accounts(self, plan_id, **filters):
        if plan_id < 1:
            raise AccountingValidationError("El plan contable no es válido.")
        return self.repository.list_accounts(plan_id=plan_id, **filters)

    def get_postable_account(self, *, plan_id, operation_date, account_id=None, account_code=None):
        if plan_id < 1 or (account_id is None) == (account_code is None):
            raise AccountingValidationError("Indica un plan y exactamente una referencia de cuenta.")
        return self.repository.get_postable_account(
            plan_id=plan_id, operation_date=operation_date,
            account_id=account_id, account_code=account_code,
        )

    def create_account(self, actor_id, plan_id, values):
        account = AccountingAccount(None, plan_id, values["code"], values["name"],
                                    values.get("parent_account_id"), values.get("normal_balance"),
                                    values.get("is_postable", False), values.get("status", "ACTIVE"),
                                    values.get("effective_from"), values.get("effective_to"))
        validate_accounting_account(account)
        if actor_id < 1:
            raise AccountingValidationError("El actor ADMIN no es válido.")
        return self.repository.create_account(values | {"plan_id": plan_id}, actor_id)

    def update_account(self, actor_id, account_id, changes):
        if actor_id < 1 or account_id < 1:
            raise AccountingValidationError("La cuenta o actor ADMIN no es válido.")
        return self.repository.update_account(account_id, changes, actor_id)

    def list_audit(self, **filters):
        return self.repository.list_audit(**filters)

    def list_periods(self, **filters):
        return self.repository.list_periods(**filters)

    def transition_period(self, actor_id, year, month, *, close, reason=None):
        if actor_id < 1:
            raise AccountingValidationError("El actor ADMIN no es válido.")
        validate_period(year, month)
        if not close and (not reason or not reason.strip()):
            raise AccountingValidationError("Indica un motivo para reabrir el periodo.")
        return self.repository.transition_period(year, month, actor_id, close=close, reason=reason)

    def period_events(self, year, month, *, limit=100, offset=0):
        validate_period(year, month)
        return self.repository.period_events(year, month, limit=limit, offset=offset)
