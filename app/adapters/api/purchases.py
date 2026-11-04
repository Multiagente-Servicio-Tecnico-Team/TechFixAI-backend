"""Rutas administrativas para registrar compras y confirmar su recepción."""
import logging
import re
from collections.abc import Callable
from datetime import date
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import SQLAlchemyError

from app.accounts.session import SessionCustomer
from app.adapters.persistence.purchases import SupplierPurchaseRepositoryAdapter
from app.application.errors import PurchaseError
from app.application.purchases import SupplierPurchaseService
from app.domain.purchases import PurchaseValidationFailure

logger = logging.getLogger(__name__)
MONEY_PATTERN = re.compile(r"^(0|[1-9][0-9]{0,11})\.[0-9]{2}$")


class SupplierWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    tax_id: str | None = Field(default=None, max_length=20)
    contact_name: str | None = Field(default=None, max_length=200)
    contact_email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=30)
    address: str | None = None
    delivery_lead_days: int | None = Field(default=None, ge=0)


class SupplierPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=200)
    tax_id: str | None = Field(default=None, max_length=20)
    contact_name: str | None = Field(default=None, max_length=200)
    contact_email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=30)
    address: str | None = None
    delivery_lead_days: int | None = Field(default=None, ge=0)
    active: bool | None = None


class PurchaseLineWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    spare_part_id: int | None = Field(default=None, ge=1)
    description: str = Field(min_length=1, max_length=300)
    quantity: Decimal = Field(gt=0, max_digits=12, decimal_places=3)
    unit_cost: str = Field(pattern=MONEY_PATTERN.pattern)
    discount_amount: str = Field(default="0.00", pattern=MONEY_PATTERN.pattern)
    tax_amount: str = Field(default="0.00", pattern=MONEY_PATTERN.pattern)


class PurchaseWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    supplier_id: int = Field(ge=1)
    purchase_order_id: int | None = Field(default=None, ge=1)
    document_type: str = Field(min_length=1, max_length=30)
    document_series: str | None = Field(default=None, max_length=30)
    document_number: str = Field(min_length=1, max_length=40)
    issue_date: date
    due_date: date | None = None
    payment_method: Literal["TRANSFER", "CASH", "CARD", "OTHER"]
    payment_status: Literal["PENDING", "PAID"]
    other_charges: str = Field(default="0.00", pattern=MONEY_PATTERN.pattern)
    notes: str | None = Field(default=None, max_length=4000)
    items: list[PurchaseLineWrite] = Field(min_length=1, max_length=100)


class PurchasePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    payment_status: Literal["PENDING", "PAID"] | None = None
    notes: str | None = Field(default=None, max_length=4000)


class ReceiptLineWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    purchase_item_id: int = Field(ge=1)
    quantity_received: Decimal = Field(gt=0, max_digits=12, decimal_places=3)


class ReceiptWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    notes: str | None = Field(default=None, max_length=2000)
    items: list[ReceiptLineWrite] = Field(min_length=1, max_length=100)


def create_supplier_purchase_router(
    *, require_admin: Callable[..., SessionCustomer], repository_factory: Callable[[], Any] | None = None,
):
    router = APIRouter(tags=["admin purchases"])
    make_repository = repository_factory or SupplierPurchaseRepositoryAdapter

    def service() -> SupplierPurchaseService:
        return SupplierPurchaseService(make_repository())

    def error_response(exc: Exception):
        if isinstance(exc, (PurchaseValidationFailure,)):
            return JSONResponse(status_code=422, content={"detail": str(exc), "code": "purchase_validation", "field": getattr(exc, "field", None)})
        if isinstance(exc, PurchaseError):
            content = {"detail": exc.detail, "code": exc.code}
            if exc.field:
                content["field"] = exc.field
            return JSONResponse(status_code=exc.status_code, content=content)
        if isinstance(exc, SQLAlchemyError):
            logger.error("Purchase API persistence failed: %s", type(exc).__name__)
            return JSONResponse(status_code=503, content={"detail": "El servicio de compras no está disponible.", "code": "purchase_storage_unavailable"})
        raise exc

    @router.get("/api/admin/suppliers")
    def list_suppliers(active: bool | None = None, search: str | None = Query(default=None, max_length=100),
                       limit: int = Query(default=50, ge=1, le=100), offset: int = Query(default=0, ge=0),
                       _actor: SessionCustomer = Depends(require_admin)):
        try:
            return service().list_suppliers(active=active, search=search, limit=limit, offset=offset)
        except (PurchaseError, SQLAlchemyError) as exc:
            return error_response(exc)

    @router.post("/api/admin/suppliers", status_code=201)
    def create_supplier(body: SupplierWrite, _actor: SessionCustomer = Depends(require_admin)):
        try:
            return {"supplier": service().create_supplier(body.model_dump())}
        except (PurchaseError, SQLAlchemyError) as exc:
            return error_response(exc)

    @router.get("/api/admin/suppliers/{supplier_id}")
    def get_supplier(supplier_id: int, _actor: SessionCustomer = Depends(require_admin)):
        try:
            return {"supplier": service().get_supplier(supplier_id)}
        except (PurchaseError, SQLAlchemyError) as exc:
            return error_response(exc)

    @router.patch("/api/admin/suppliers/{supplier_id}")
    def update_supplier(supplier_id: int, body: SupplierPatch, _actor: SessionCustomer = Depends(require_admin)):
        try:
            return {"supplier": service().update_supplier(supplier_id, body.model_dump(exclude_unset=True))}
        except (PurchaseError, SQLAlchemyError) as exc:
            return error_response(exc)

    @router.get("/api/admin/purchases")
    def list_purchases(supplier_id: int | None = Query(default=None, ge=1), from_date: date | None = None,
                       to_date: date | None = None, status: str | None = None,
                       payment_status: str | None = None, document_number: str | None = Query(default=None, max_length=40),
                       limit: int = Query(default=50, ge=1, le=100), offset: int = Query(default=0, ge=0),
                       _actor: SessionCustomer = Depends(require_admin)):
        try:
            return service().list_purchases(supplier_id=supplier_id, from_date=from_date, to_date=to_date,
                status=status, payment_status=payment_status, document_number=document_number, limit=limit, offset=offset)
        except (PurchaseError, SQLAlchemyError) as exc:
            return error_response(exc)

    @router.post("/api/admin/purchases", status_code=201)
    def create_purchase(body: PurchaseWrite, actor: SessionCustomer = Depends(require_admin)):
        try:
            purchase = service().create_purchase(actor_id=actor.id, values=body.model_dump(mode="python"))
            return {"purchase": purchase}
        except (PurchaseError, PurchaseValidationFailure, SQLAlchemyError) as exc:
            return error_response(exc)

    @router.get("/api/admin/purchases/{purchase_id}")
    def get_purchase(purchase_id: int, _actor: SessionCustomer = Depends(require_admin)):
        try:
            return {"purchase": service().get_purchase(purchase_id)}
        except (PurchaseError, SQLAlchemyError) as exc:
            return error_response(exc)

    @router.patch("/api/admin/purchases/{purchase_id}")
    def update_purchase(purchase_id: int, body: PurchasePatch, actor: SessionCustomer = Depends(require_admin)):
        try:
            values = body.model_dump(exclude_unset=True)
            return {"purchase": service().update_purchase(actor_id=actor.id, purchase_id=purchase_id, values=values)}
        except (PurchaseError, SQLAlchemyError) as exc:
            return error_response(exc)

    @router.post("/api/admin/purchases/{purchase_id}/cancel")
    def cancel_purchase(purchase_id: int, actor: SessionCustomer = Depends(require_admin)):
        try:
            return {"purchase": service().cancel_purchase(actor_id=actor.id, purchase_id=purchase_id)}
        except (PurchaseError, SQLAlchemyError) as exc:
            return error_response(exc)

    @router.post("/api/admin/purchases/{purchase_id}/receipts", status_code=201)
    def receive_purchase(purchase_id: int, body: ReceiptWrite, response: Response,
                         idempotency_key: UUID = Header(alias="Idempotency-Key"),
                         actor: SessionCustomer = Depends(require_admin)):
        try:
            receipt, replay = service().receive_purchase(actor_id=actor.id, purchase_id=purchase_id,
                idempotency_key=idempotency_key, items=[line.model_dump() for line in body.items], notes=body.notes)
            if replay:
                response.status_code = 200
                response.headers["Idempotent-Replayed"] = "true"
            return {"receipt": receipt}
        except (PurchaseError, SQLAlchemyError) as exc:
            return error_response(exc)

    @router.get("/api/admin/purchases/{purchase_id}/receipts")
    def list_receipts(purchase_id: int, _actor: SessionCustomer = Depends(require_admin)):
        try:
            return {"items": service().list_receipts(purchase_id)}
        except (PurchaseError, SQLAlchemyError) as exc:
            return error_response(exc)

    return router
