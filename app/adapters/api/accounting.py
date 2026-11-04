"""Rutas administrativas para el registro interno de asientos."""
import logging
import re
from datetime import date
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Response
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.exc import SQLAlchemyError

from app.application.accounting import AccountingService
from app.application.errors import AccountingError
from app.domain.accounting import AccountingValidationError, EntryDraft, EntryLine

logger = logging.getLogger(__name__)
MONEY_PATTERN = re.compile(r"^(0|[1-9][0-9]{0,11})\.[0-9]{2}$")


class EntryLineIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    account_code: str = Field(min_length=1, max_length=40)
    account_name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=1000)
    debit: str = Field(pattern=MONEY_PATTERN.pattern)
    credit: str = Field(pattern=MONEY_PATTERN.pattern)

    @model_validator(mode="after")
    def exactly_one_positive_side(self):
        debit, credit = Decimal(self.debit), Decimal(self.credit)
        if (debit > 0) == (credit > 0):
            raise ValueError("Cada línea requiere debe o haber positivo, pero no ambos.")
        return self


class CreateEntryIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation_date: date
    concept: str = Field(min_length=1, max_length=200)
    detail: str = Field(min_length=1, max_length=4000)
    category_id: int = Field(ge=1)
    lines: list[EntryLineIn] = Field(min_length=2, max_length=100)

    def to_draft(self) -> EntryDraft:
        return EntryDraft(
            self.operation_date, self.concept, self.detail, self.category_id,
            tuple(EntryLine(line.account_code, line.account_name, line.description,
                            Decimal(line.debit), Decimal(line.credit)) for line in self.lines),
        )


class ReverseEntryIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation_date: date
    reason: str = Field(min_length=1, max_length=2000)


def create_accounting_router(repository_factory, require_admin):
    router = APIRouter(prefix="/api/admin/accounting", tags=["accounting"])

    def service() -> AccountingService:
        return AccountingService(repository_factory())

    def error_response(exc: Exception):
        from fastapi.responses import JSONResponse
        if isinstance(exc, AccountingValidationError):
            return JSONResponse(status_code=422, content={"detail": str(exc), "code": "accounting_validation"})
        if isinstance(exc, AccountingError):
            return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail, "code": exc.code})
        if isinstance(exc, SQLAlchemyError):
            logger.error("Accounting API persistence failed: %s", type(exc).__name__)
            return JSONResponse(status_code=503, content={"detail": "El servicio contable no está disponible.", "code": "accounting_storage_unavailable"})
        raise exc

    @router.get("/categories")
    def list_categories(_actor=Depends(require_admin)):
        try:
            return {"items": service().list_categories()}
        except (AccountingError, AccountingValidationError, SQLAlchemyError) as exc:
            return error_response(exc)

    @router.post("/entries", status_code=201)
    def create_entry(
        body: CreateEntryIn,
        response: Response,
        idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
        actor=Depends(require_admin),
    ):
        try:
            entry, replayed = service().create_entry(actor_id=actor.id, idempotency_key=idempotency_key, draft=body.to_draft())
            if replayed:
                response.status_code = 200
                response.headers["Idempotent-Replayed"] = "true"
            return entry
        except (AccountingError, AccountingValidationError, SQLAlchemyError) as exc:
            return error_response(exc)

    @router.get("/entries")
    def list_entries(
        _actor=Depends(require_admin),
        from_date: date | None = None,
        to_date: date | None = None,
        category_id: int | None = Query(default=None, ge=1),
        status: str | None = Query(default=None, pattern="^(CONFIRMED|REVERSED)$"),
        entry_number: int | None = Query(default=None, ge=1),
        limit: int = Query(default=50, ge=1, le=100),
        offset: int = Query(default=0, ge=0),
    ):
        if from_date and to_date and from_date > to_date:
            return error_response(AccountingValidationError("El rango de fechas no es válido."))
        try:
            return service().list_entries(from_date=from_date, to_date=to_date, category_id=category_id,
                                          status=status, entry_number=entry_number, limit=limit, offset=offset)
        except (AccountingError, AccountingValidationError, SQLAlchemyError) as exc:
            return error_response(exc)

    @router.get("/entries/{entry_id}")
    def get_entry(entry_id: int, _actor=Depends(require_admin)):
        if entry_id < 1:
            return error_response(AccountingValidationError("El identificador no es válido."))
        try:
            return service().get_entry(entry_id)
        except (AccountingError, AccountingValidationError, SQLAlchemyError) as exc:
            return error_response(exc)

    @router.post("/entries/{entry_id}/reverse", status_code=201)
    def reverse_entry(entry_id: int, body: ReverseEntryIn, response: Response, actor=Depends(require_admin)):
        try:
            result, replayed = service().reverse_entry(actor_id=actor.id, entry_id=entry_id,
                                                       operation_date=body.operation_date, reason=body.reason)
            if replayed:
                response.status_code = 200
            return result
        except (AccountingError, AccountingValidationError, SQLAlchemyError) as exc:
            return error_response(exc)

    return router
