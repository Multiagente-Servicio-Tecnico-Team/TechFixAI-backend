"""Contratos HTTP ADMIN para catálogo y periodos contables."""
import logging
import re
from datetime import date, datetime

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.exc import SQLAlchemyError

from app.adapters.persistence.accounting_catalog import AccountingCatalogRepository
from app.application.accounting_catalog import AccountingCatalogService
from app.application.errors import AccountingError
from app.domain.accounting import AccountingValidationError, validate_period

logger = logging.getLogger(__name__)
PERIOD_PATTERN = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def validate_period_range(from_period: str | None, to_period: str | None) -> None:
    for value in (from_period, to_period):
        if value is not None and not PERIOD_PATTERN.fullmatch(value):
            raise AccountingValidationError("El periodo debe usar el formato YYYY-MM y un mes entre 01 y 12.")
        if value is not None and int(value[:4]) < 2000:
            raise AccountingValidationError("El año del periodo debe ser igual o posterior a 2000.")
    if from_period is not None and to_period is not None and from_period > to_period:
        raise AccountingValidationError("El periodo inicial no puede ser posterior al final.")


class PlanIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(min_length=1, max_length=40)
    edition: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=160)
    jurisdiction: str = Field(min_length=2, max_length=8)
    source_name: str | None = Field(default=None, max_length=160)
    source_url: str | None = Field(default=None, max_length=1000)
    effective_from: date | None = None
    effective_to: date | None = None

    @model_validator(mode="after")
    def validate_dates(self):
        if self.effective_from and self.effective_to and self.effective_to < self.effective_from:
            raise ValueError("La vigencia final no puede preceder a la inicial.")
        return self


class AccountIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=200)
    parent_account_id: int | None = Field(default=None, ge=1)
    account_group: str | None = Field(default=None, max_length=40)
    normal_balance: str = Field(pattern="^(DEBIT|CREDIT)$")
    is_postable: bool = False
    status: str = Field(default="ACTIVE", pattern="^(ACTIVE|INACTIVE)$")
    effective_from: date | None = None
    effective_to: date | None = None


class AccountPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=200)
    account_group: str | None = Field(default=None, max_length=40)
    normal_balance: str | None = Field(default=None, pattern="^(DEBIT|CREDIT)$")
    is_postable: bool | None = None
    status: str | None = Field(default=None, pattern="^(ACTIVE|INACTIVE)$")
    effective_to: date | None = None

    @model_validator(mode="after")
    def require_changes(self):
        if not self.model_fields_set:
            raise ValueError("Indica al menos un cambio.")
        return self


class ReopenPeriodIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=1, max_length=2000)


def create_accounting_catalog_router(require_admin, repository_factory=None):
    router = APIRouter(prefix="/api/admin/accounting", tags=["accounting-catalog"])
    repo_factory = repository_factory or AccountingCatalogRepository

    def repo():
        return repo_factory()

    def service():
        return AccountingCatalogService(repo())

    def error(exc: Exception):
        if isinstance(exc, AccountingValidationError):
            return JSONResponse(status_code=422, content={"detail": str(exc), "code": "accounting_validation"})
        if isinstance(exc, AccountingError):
            return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail, "code": exc.code})
        if isinstance(exc, SQLAlchemyError):
            logger.error("Accounting catalog API failed: %s", type(exc).__name__)
            return JSONResponse(status_code=503, content={"detail": "El servicio contable no está disponible.", "code": "accounting_storage_unavailable"})
        raise exc

    @router.get("/plans")
    def list_plans(_actor=Depends(require_admin)):
        try:
            return {"items": service().list_plans()}
        except (AccountingError, AccountingValidationError, SQLAlchemyError) as exc:
            return error(exc)

    @router.post("/plans", status_code=201)
    def create_plan(body: PlanIn, actor=Depends(require_admin)):
        try:
            return service().create_plan(actor.id, body.model_dump())
        except (AccountingError, AccountingValidationError, SQLAlchemyError) as exc:
            return error(exc)

    @router.put("/plans/{plan_id}/default")
    def set_default_plan(plan_id: int, actor=Depends(require_admin)):
        try:
            return service().set_default_plan(plan_id, actor.id)
        except (AccountingError, AccountingValidationError, SQLAlchemyError) as exc:
            return error(exc)

    @router.get("/plans/{plan_id}/accounts")
    def list_accounts(plan_id: int, _actor=Depends(require_admin), q: str | None = Query(default=None, max_length=120),
                      parent_id: int | None = Query(default=None, ge=1),
                      postable: bool | None = None,
                      status: str | None = Query(default=None, pattern="^(ACTIVE|INACTIVE)$"),
                      limit: int = Query(default=50, ge=1, le=100), offset: int = Query(default=0, ge=0)):
        try:
            return service().list_accounts(plan_id, q=q,
                parent_account_id=parent_id, is_postable=postable,
                status=status, limit=limit, offset=offset)
        except (AccountingError, AccountingValidationError, SQLAlchemyError) as exc:
            return error(exc)

    @router.post("/plans/{plan_id}/accounts", status_code=201)
    def create_account(plan_id: int, body: AccountIn, actor=Depends(require_admin)):
        try:
            return service().create_account(actor.id, plan_id, body.model_dump())
        except (AccountingError, AccountingValidationError, SQLAlchemyError) as exc:
            return error(exc)

    @router.patch("/accounts/{account_id}")
    def update_account(account_id: int, body: AccountPatch, actor=Depends(require_admin)):
        try:
            return service().update_account(actor.id, account_id, body.model_dump(exclude_unset=True))
        except (AccountingError, AccountingValidationError, SQLAlchemyError) as exc:
            return error(exc)

    @router.get("/audit-events")
    def list_audit(_actor=Depends(require_admin),
                   entity_type: str | None = Query(default=None, pattern="^(PLAN|ACCOUNT|DEFAULT_PLAN|PERIOD)$"),
                   from_at: datetime | None = None, to_at: datetime | None = None,
                   limit: int = Query(default=50, ge=1, le=100), offset: int = Query(default=0, ge=0)):
        try:
            if from_at is not None and to_at is not None and from_at > to_at:
                raise AccountingValidationError("from_at no puede ser posterior a to_at.")
            return service().list_audit(entity_type=entity_type, from_at=from_at, to_at=to_at,
                                     limit=limit, offset=offset)
        except (AccountingError, AccountingValidationError, SQLAlchemyError) as exc:
            return error(exc)

    @router.get("/periods")
    def list_periods(_actor=Depends(require_admin), from_period: str | None = None, to_period: str | None = None,
                     status: str | None = Query(default=None, pattern="^(OPEN|CLOSED)$"),
                     limit: int = Query(default=100, ge=1, le=100), offset: int = Query(default=0, ge=0)):
        try:
            validate_period_range(from_period, to_period)
            return service().list_periods(from_period=from_period, to_period=to_period, status=status,
                                       limit=limit, offset=offset)
        except (AccountingError, AccountingValidationError, SQLAlchemyError) as exc:
            return error(exc)

    @router.post("/periods/{year}/{month}/close")
    def close_period(year: int, month: int, actor=Depends(require_admin)):
        try:
            validate_period(year, month)
            return service().transition_period(actor.id, year, month, close=True)
        except (AccountingError, AccountingValidationError, SQLAlchemyError) as exc:
            return error(exc)

    @router.post("/periods/{year}/{month}/reopen")
    def reopen_period(year: int, month: int, body: ReopenPeriodIn, actor=Depends(require_admin)):
        try:
            validate_period(year, month)
            return service().transition_period(actor.id, year, month, close=False, reason=body.reason)
        except (AccountingError, AccountingValidationError, SQLAlchemyError) as exc:
            return error(exc)

    @router.get("/periods/{year}/{month}/events")
    def period_events(year: int, month: int, _actor=Depends(require_admin),
                      limit: int = Query(default=100, ge=1, le=100), offset: int = Query(default=0, ge=0)):
        try:
            validate_period(year, month)
            return service().period_events(year, month, limit=limit, offset=offset)
        except (AccountingError, AccountingValidationError, SQLAlchemyError) as exc:
            return error(exc)

    return router
