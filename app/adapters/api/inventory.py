"""Rutas CRUD del catálogo para personal autenticado del taller."""
import re
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Depends, Response
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
    current_stock: int = Field(ge=0, le=999999, strict=True)
    minimum_threshold: int = Field(ge=0, le=999999, strict=True)

    def values(self) -> dict[str, object]:
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
    def create_part(body: InventoryPartWrite, _staff: SessionCustomer = Depends(require_staff)):
        try:
            part = service().create_part(body.values())
            return {"part": _part_response(part)}
        except InventoryError as exc:
            return _error_response(exc)

    @router.put("/parts/{code}")
    def update_part(code: str, body: InventoryPartWrite, _staff: SessionCustomer = Depends(require_staff)):
        try:
            part = service().update_part(code, body.values())
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

    return router
