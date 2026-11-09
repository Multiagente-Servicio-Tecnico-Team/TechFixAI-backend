"""ADMIN API for supplier purchase-order lifecycle."""
import logging
import re
from collections.abc import Callable
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, Header, Path, Query, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import SQLAlchemyError
from uuid import UUID

from app.accounts.session import SessionCustomer
from app.adapters.persistence.purchase_orders import PurchaseOrderRepositoryAdapter
from app.application.errors import PurchaseOrderError
from app.application.purchase_orders import PurchaseOrderService

logger = logging.getLogger(__name__)
MONEY_PATTERN = re.compile(r"^(0|[1-9][0-9]{0,11})\.[0-9]{2}$")


class PurchaseOrderLineWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    spare_part_id: int | None = Field(default=None, ge=1)
    description: str = Field(min_length=1, max_length=300)
    quantity: int = Field(ge=1, le=999_999)
    unit_cost: str = Field(pattern=MONEY_PATTERN.pattern)


class PurchaseOrderWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    supplier_id: int = Field(ge=1)
    estimated_arrival: date | None = None
    notes: str | None = Field(default=None, max_length=2000)
    items: list[PurchaseOrderLineWrite] = Field(min_length=1, max_length=100)


class PurchaseOrderPatch(BaseModel):
    model_config = ConfigDict(extra="forbid", min_properties=1)
    supplier_id: int | None = Field(default=None, ge=1)
    estimated_arrival: date | None = None
    notes: str | None = Field(default=None, max_length=2000)
    items: list[PurchaseOrderLineWrite] | None = Field(default=None, min_length=1, max_length=100)


class PurchaseOrderCancelWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=1, max_length=500)


class PurchaseOrderReceiptLineWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    purchase_order_item_id: int = Field(ge=1)
    quantity_received: int = Field(ge=1, le=999_999)


class PurchaseOrderReceiptWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    notes: str | None = Field(default=None, max_length=2000)
    items: list[PurchaseOrderReceiptLineWrite] = Field(min_length=1, max_length=100)


def create_purchase_order_router(
    *,
    require_admin: Callable[..., SessionCustomer],
    repository_factory: Callable[[], Any] | None = None,
):
    router = APIRouter(tags=["admin purchase orders"])
    make_repository = repository_factory or PurchaseOrderRepositoryAdapter

    def service() -> PurchaseOrderService:
        return PurchaseOrderService(make_repository())

    @router.get("/api/admin/purchase-orders")
    def list_orders(
        supplier_id: int | None = Query(default=None, ge=1),
        status: str | None = Query(default=None),
        date_from: date | None = None,
        date_to: date | None = None,
        limit: int = Query(default=50, ge=1, le=100),
        offset: int = Query(default=0, ge=0),
        _actor: SessionCustomer = Depends(require_admin),
    ):
        try:
            return service().list_orders(supplier_id=supplier_id, status=status, date_from=date_from,
                                         date_to=date_to, limit=limit, offset=offset)
        except (PurchaseOrderError, SQLAlchemyError) as exc:
            return error_response(exc)

    def error_response(exc: Exception):
        if isinstance(exc, PurchaseOrderError):
            content = {"detail": exc.detail, "code": exc.code}
            if exc.field:
                content["field"] = exc.field
            return JSONResponse(status_code=exc.status_code, content=content)
        if isinstance(exc, SQLAlchemyError):
            logger.error("Purchase order API persistence failed: %s", type(exc).__name__)
            return JSONResponse(status_code=503, content={
                "detail": "El servicio de órdenes de compra no está disponible.",
                "code": "purchase_order_storage_unavailable",
            })
        raise exc

    @router.post("/api/admin/purchase-orders", status_code=201)
    def create_order(body: PurchaseOrderWrite, actor: SessionCustomer = Depends(require_admin)):
        try:
            order = service().create_order(actor_id=actor.id, values=body.model_dump(mode="python"))
            return {"order": order}
        except (PurchaseOrderError, SQLAlchemyError) as exc:
            return error_response(exc)

    @router.get("/api/admin/purchase-orders/{order_id}")
    def get_order(order_id: int = Path(ge=1), _actor: SessionCustomer = Depends(require_admin)):
        try:
            return {"order": service().get_order(order_id)}
        except (PurchaseOrderError, SQLAlchemyError) as exc:
            return error_response(exc)

    @router.patch("/api/admin/purchase-orders/{order_id}")
    def update_draft_order(
        order_id: int = Path(ge=1),
        body: PurchaseOrderPatch = ...,
        actor: SessionCustomer = Depends(require_admin),
    ):
        try:
            order = service().update_draft_order(
                actor_id=actor.id,
                order_id=order_id,
                values=body.model_dump(exclude_unset=True, mode="python"),
            )
            return {"order": order}
        except (PurchaseOrderError, SQLAlchemyError) as exc:
            return error_response(exc)

    @router.post("/api/admin/purchase-orders/{order_id}/issue")
    def issue_order(order_id: int = Path(ge=1), actor: SessionCustomer = Depends(require_admin)):
        try:
            return {"order": service().issue_order(actor_id=actor.id, order_id=order_id)}
        except (PurchaseOrderError, SQLAlchemyError) as exc:
            return error_response(exc)

    @router.post("/api/admin/purchase-orders/{order_id}/cancel")
    def cancel_order(
        body: PurchaseOrderCancelWrite,
        order_id: int = Path(ge=1),
        actor: SessionCustomer = Depends(require_admin),
    ):
        try:
            return {"order": service().cancel_order(
                actor_id=actor.id, order_id=order_id, reason=body.reason
            )}
        except (PurchaseOrderError, SQLAlchemyError) as exc:
            return error_response(exc)

    @router.post("/api/admin/purchase-orders/{order_id}/receipts", status_code=201)
    def receive_order(
        body: PurchaseOrderReceiptWrite,
        response: Response,
        order_id: int = Path(ge=1),
        idempotency_key: UUID = Header(alias="Idempotency-Key"),
        actor: SessionCustomer = Depends(require_admin),
    ):
        try:
            receipt, replay = service().receive_order(
                actor_id=actor.id,
                order_id=order_id,
                idempotency_key=idempotency_key,
                values={"items": [item.model_dump() for item in body.items], "notes": body.notes},
            )
            if replay:
                response.status_code = 200
                response.headers["Idempotent-Replayed"] = "true"
            return {"receipt": receipt}
        except (PurchaseOrderError, SQLAlchemyError) as exc:
            return error_response(exc)

    @router.get("/api/admin/purchase-orders/{order_id}/receipts")
    def list_order_receipts(order_id: int = Path(ge=1), _actor: SessionCustomer = Depends(require_admin)):
        try:
            return {"items": service().list_receipts(order_id)}
        except (PurchaseOrderError, SQLAlchemyError) as exc:
            return error_response(exc)

    return router
