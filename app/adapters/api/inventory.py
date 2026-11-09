"""Rutas CRUD del catálogo para personal autenticado del taller."""
import re
import hashlib
import json
from collections.abc import Callable
from datetime import date
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from app.accounts.session import SessionCustomer
from app.adapters.persistence.inventory import InventoryRepositoryAdapter
from app.application.errors import InventoryError
from app.application.inventory import InventoryService
from app.domain.inventory import InventoryPart, part_to_dict

PRICE_PATTERN = re.compile(r"^(0|[1-9][0-9]{0,7})\.[0-9]{2}$")


class InventoryPartWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=50, pattern=r"^[A-Z0-9]+(?:-[A-Z0-9]+)*$")
    name: str = Field(min_length=3, max_length=150)
    category: str = Field(min_length=1, max_length=50)
    description: str | None = None
    unit_price: str = Field(pattern=PRICE_PATTERN.pattern)
    current_stock: int | None = Field(default=None, ge=0, le=999999, strict=True, deprecated=True)
    minimum_threshold: int = Field(ge=0, le=999999, strict=True)

    def values(self) -> dict[str, object]:
        return self.model_dump()


class StockCountWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    counted_stock: int = Field(ge=0, le=999999, strict=True)
    reason: str = Field(min_length=1, max_length=500)

    def values(self):
        return self.model_dump()


def _part_response(part: InventoryPart) -> dict[str, object]:
    return part_to_dict(part)


def _error_response(exc: InventoryError) -> JSONResponse:
    content: dict[str, object] = {"detail": exc.detail, "code": exc.code}
    if exc.field:
        content["field"] = exc.field
    return JSONResponse(status_code=exc.status_code, content=content)


def create_inventory_router(
    *,
    require_staff: Callable[..., SessionCustomer],
    repository_factory: Callable[[], Any] | None = None,
):
    router = APIRouter(prefix="/api/inventory", tags=["inventory"])
    make_repository = repository_factory or InventoryRepositoryAdapter

    def service() -> InventoryService:
        return InventoryService(make_repository())

    @router.get("/parts")
    def list_parts(_staff: SessionCustomer = Depends(require_staff)):
        try:
            return {"parts": [_part_response(part) for part in service().list_parts()]}
        except InventoryError as exc:
            return _error_response(exc)

    @router.get("/categories")
    def list_categories(_staff: SessionCustomer = Depends(require_staff)):
        try:
            return {"categories": service().list_categories()}
        except InventoryError as exc:
            return _error_response(exc)

    @router.post("/parts", status_code=201)
    def create_part(body: InventoryPartWrite, staff: SessionCustomer = Depends(require_staff)):
        try:
            part = service().create_part(body.values(), actor_id=staff.id)
            return {"part": _part_response(part)}
        except InventoryError as exc:
            return _error_response(exc)

    @router.put("/parts/{code}")
    def update_part(code: str, body: InventoryPartWrite, staff: SessionCustomer = Depends(require_staff)):
        try:
            part = service().update_part(code, body.values(), actor_id=staff.id)
            return {"part": _part_response(part)}
        except InventoryError as exc:
            return _error_response(exc)

    @router.delete("/parts/{code}", status_code=204)
    def delete_part(code: str, _staff: SessionCustomer = Depends(require_staff)):
        try:
            service().delete_part(code)
            return Response(status_code=204)
        except InventoryError as exc:
            return _error_response(exc)

    def stock_operation(body, *, part_id, operation):
        canonical = {"operation": operation, "part_id": part_id, "payload": body}
        request_hash = hashlib.sha256(json.dumps(canonical, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
        return body, request_hash

    @router.post("/parts/{part_id}/opening-balance", status_code=201)
    def opening_balance(part_id: int, body: StockCountWrite, staff: SessionCustomer = Depends(require_staff),
                        idempotency_key: UUID = Header(alias="Idempotency-Key")):
        try:
            values, digest = stock_operation(body.model_dump(), part_id=part_id, operation="OPENING_BALANCE")
            result = service().record_opening_balance(part_id=part_id, count=values["counted_stock"],
                actor_id=staff.id, reason=values["reason"], idempotency_key=idempotency_key, request_hash=digest)
            replayed = result.pop("replayed", False)
            return JSONResponse(status_code=200 if replayed or not result.get("changed") else 201, content=result,
                headers={"Idempotent-Replayed": "true"} if replayed else None)
        except InventoryError as exc:
            return _error_response(exc)

    @router.post("/parts/{part_id}/adjustments")
    def adjust_stock(part_id: int, body: StockCountWrite, staff: SessionCustomer = Depends(require_staff),
                     idempotency_key: UUID = Header(alias="Idempotency-Key")):
        try:
            values, digest = stock_operation(body.model_dump(), part_id=part_id, operation="ADJUSTMENT")
            result = service().adjust_stock(part_id=part_id, count=values["counted_stock"],
                actor_id=staff.id, reason=values["reason"], idempotency_key=idempotency_key, request_hash=digest)
            replayed = result.pop("replayed", False)
            headers = {"Idempotent-Replayed": "true"} if replayed else None
            return JSONResponse(status_code=200 if replayed or not result.get("changed") else 201, content=result, headers=headers)
        except InventoryError as exc:
            return _error_response(exc)

    @router.get("/parts/{part_id}/movements")
    def list_movements(part_id: int, movement_type: str | None = None, from_date: date | None = None,
                       to_date: date | None = None, limit: int = Query(default=50, ge=1, le=200),
                       offset: int = Query(default=0, ge=0), _staff: SessionCustomer = Depends(require_staff)):
        allowed = {"OPENING_BALANCE", "ADJUSTMENT_IN", "ADJUSTMENT_OUT", "PURCHASE_RECEIPT", "SALE"}
        if movement_type is not None and movement_type not in allowed:
            return JSONResponse(status_code=422, content={"detail": "El tipo de movimiento no es válido.", "code": "invalid", "field": "movement_type"})
        if from_date and to_date and from_date > to_date:
            return JSONResponse(status_code=422, content={"detail": "El rango de fechas no es válido.", "code": "invalid"})
        try:
            return service().list_movements(part_id=part_id, movement_type=movement_type,
                from_date=from_date, to_date=to_date, limit=limit, offset=offset)
        except InventoryError as exc:
            return _error_response(exc)

    return router
