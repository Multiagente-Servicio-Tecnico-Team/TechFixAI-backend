"""ADMIN and owner-scoped endpoints for direct product quotations and sales."""
from collections.abc import Callable
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.accounts.session import SessionCustomer
from app.adapters.persistence.sales_quotes import SalesQuoteRepositoryAdapter


class QuoteLineWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    spare_part_id: int = Field(gt=0)
    quantity: int = Field(gt=0, le=1000)


class SalesQuoteWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    customer_id: int | None = Field(default=None, gt=0)
    lines: list[QuoteLineWrite] = Field(min_length=1, max_length=50)
    observations: str | None = Field(default=None, max_length=2000)
    expires_at: datetime


class PaymentConfirmation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    method: Literal["CREDIT_CARD", "DEBIT_CARD", "BANK_TRANSFER", "CASH", "PAYMENT_GATEWAY"]
    transaction_reference: str | None = Field(default=None, max_length=100)
    notes: str | None = Field(default=None, max_length=1000)


class ManualAcceptance(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirmation_channel: Literal["IN_PERSON", "PHONE", "OTHER"]
    notes: str | None = Field(default=None, max_length=1000)


class QuoteCancellation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    notes: str | None = Field(default=None, max_length=1000)


def create_sales_quote_router(*, require_admin: Callable[..., SessionCustomer],
                              require_customer: Callable[..., SessionCustomer], repository_factory=None):
    router = APIRouter(tags=["cotizaciones de venta"])
    make_repository = repository_factory or SalesQuoteRepositoryAdapter

    @router.get("/api/admin/sales-quotes")
    def admin_list_quotes(customer_id: int | None = Query(default=None, gt=0),
                          status: str | None = None,
                          limit: int = Query(default=50, ge=1, le=200),
                          offset: int = Query(default=0, ge=0),
                          _admin: SessionCustomer = Depends(require_admin)):
        try:
            rows = make_repository().list_sales_quotes(customer_id=customer_id, status=status, limit=limit, offset=offset)
            return {"items": rows, "limit": limit, "offset": offset}
        except SQLAlchemyError as exc:
            raise HTTPException(503, "No se pudieron consultar las cotizaciones.") from exc

    @router.post("/api/admin/sales-quotes", status_code=201)
    def admin_create_quote(body: SalesQuoteWrite, admin: SessionCustomer = Depends(require_admin)):
        if body.customer_id is None:
            raise HTTPException(422, "customer_id es obligatorio para ADMIN.")
        try:
            return make_repository().create_direct_sales_quote(
                customer_id=body.customer_id, actor_user_id=admin.id,
                lines=[line.model_dump() for line in body.lines], expires_at=body.expires_at,
                observations=body.observations,
            )
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        except (IntegrityError, SQLAlchemyError) as exc:
            raise HTTPException(503, "No se pudo registrar la cotización.") from exc

    @router.get("/api/admin/sales-quotes/{quote_id}")
    def admin_get_quote(quote_id: int, _admin: SessionCustomer = Depends(require_admin)):
        try:
            row = make_repository().get_sales_quote(quote_id)
        except SQLAlchemyError as exc:
            raise HTTPException(503, "No se pudo cargar la cotización.") from exc
        if row is None:
            raise HTTPException(404, "Cotización no encontrada.")
        return row

    @router.post("/api/admin/sales-quotes/{quote_id}/acceptance")
    def admin_accept_quote(quote_id: int, body: ManualAcceptance,
                           idempotency_key: str = Header(alias="Idempotency-Key", min_length=1, max_length=200),
                           admin: SessionCustomer = Depends(require_admin)):
        try:
            repo = make_repository()
            quote = repo.get_sales_quote(quote_id)
            if quote is None:
                raise HTTPException(404, "Cotización no encontrada.")
            result = repo.accept_direct_sales_quote(quote_id=quote_id,
                customer_id=int(quote["customer_id"]), actor_user_id=admin.id,
                idempotency_key=idempotency_key,
                confirmation_channel=body.confirmation_channel, notes=body.notes)
            if result.get("error"):
                raise HTTPException(409, result["error"])
            return {"quote": repo.get_sales_quote(quote_id), **result}
        except HTTPException:
            raise
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        except SQLAlchemyError as exc:
            raise HTTPException(503, "No se pudo aceptar la cotización.") from exc

    @router.post("/api/admin/sales-quotes/{quote_id}/payment-confirmation", status_code=201)
    def admin_confirm_payment(quote_id: int, body: PaymentConfirmation,
                              idempotency_key: str = Header(alias="Idempotency-Key", min_length=1, max_length=200),
                              admin: SessionCustomer = Depends(require_admin)):
        try:
            result = make_repository().confirm_direct_sales_payment(
                quote_id=quote_id, actor_user_id=admin.id, idempotency_key=idempotency_key,
                method=body.method, transaction_reference=body.transaction_reference, notes=body.notes)
            if result.get("error"):
                raise HTTPException(409, result["error"])
            return result
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        except (IntegrityError, SQLAlchemyError) as exc:
            raise HTTPException(503, "No se pudo confirmar el pago.") from exc

    @router.get("/api/customer/sales-quotes")
    def customer_quotes(customer: SessionCustomer = Depends(require_customer)):
        customer_id = customer.commercial_customer_id or customer.id
        try:
            return {"items": make_repository().list_sales_quotes(customer_id=customer_id)}
        except SQLAlchemyError as exc:
            raise HTTPException(503, "No se pudieron consultar tus cotizaciones.") from exc

    @router.post("/api/customer/sales-quotes/{quote_id}/acceptance")
    def customer_accept_quote(quote_id: int,
                              idempotency_key: str = Header(alias="Idempotency-Key", min_length=1, max_length=200),
                              customer: SessionCustomer = Depends(require_customer)):
        customer_id = customer.commercial_customer_id or customer.id
        try:
            repo = make_repository()
            result = repo.accept_direct_sales_quote(
                quote_id=quote_id, customer_id=customer_id,
                actor_user_id=customer.id, idempotency_key=idempotency_key)
            if result.get("error"):
                raise HTTPException(409, result["error"])
            return {"quote": repo.get_sales_quote(quote_id, customer_id=customer_id), **result}
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(404, "Cotización no encontrada.") from exc
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        except SQLAlchemyError as exc:
            raise HTTPException(503, "No se pudo aceptar la cotización.") from exc

    @router.post("/api/admin/sales-quotes/{quote_id}/cancellation")
    def admin_cancel_quote(quote_id: int, body: QuoteCancellation,
                           admin: SessionCustomer = Depends(require_admin)):
        try:
            repo = make_repository()
            result = repo.resolve_direct_sales_quote(
                quote_id=quote_id, customer_id=None, actor_user_id=admin.id,
                target_status="CANCELLED", notes=body.notes)
            return {"quote": repo.get_sales_quote(quote_id), **result}
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        except SQLAlchemyError as exc:
            raise HTTPException(503, "No se pudo cancelar la cotización.") from exc

    @router.get("/api/admin/sales-orders")
    def admin_list_orders(customer_id: int | None = Query(default=None, gt=0),
                          limit: int = Query(default=50, ge=1, le=200),
                          offset: int = Query(default=0, ge=0),
                          _admin: SessionCustomer = Depends(require_admin)):
        try:
            return {"items": make_repository().list_sales_orders(
                customer_id=customer_id, limit=limit, offset=offset), "limit": limit, "offset": offset}
        except SQLAlchemyError as exc:
            raise HTTPException(503, "No se pudieron consultar las ventas.") from exc

    @router.get("/api/admin/sales-orders/{order_id}")
    def admin_get_order(order_id: int, _admin: SessionCustomer = Depends(require_admin)):
        try:
            row = make_repository().get_sales_order(order_id)
        except SQLAlchemyError as exc:
            raise HTTPException(503, "No se pudo cargar la venta.") from exc
        if row is None:
            raise HTTPException(404, "Venta no encontrada.")
        return row

    @router.get("/api/customer/quotes")
    def customer_list_quotes(status: str | None = None, limit: int = Query(default=50, ge=1, le=100),
                             offset: int = Query(default=0, ge=0),
                             customer: SessionCustomer = Depends(require_customer)):
        customer_id = customer.commercial_customer_id or customer.id
        try:
            return {"items": make_repository().list_customer_quotes(
                customer_id=customer_id, status=status, limit=limit, offset=offset)}
        except SQLAlchemyError as exc:
            raise HTTPException(503, "No se pudieron consultar tus cotizaciones.") from exc

    @router.get("/api/customer/quotes/{quote_id}")
    def customer_get_quote(quote_id: int, customer: SessionCustomer = Depends(require_customer)):
        try:
            row = make_repository().get_commercial_quote(
                quote_id, customer_id=customer.commercial_customer_id or customer.id)
        except SQLAlchemyError as exc:
            raise HTTPException(503, "No se pudo cargar la cotización.") from exc
        if row is None:
            raise HTTPException(404, "Cotización no encontrada.")
        return row

    @router.post("/api/customer/quotes/{quote_id}/acceptance")
    def customer_accept_commercial_quote(quote_id: int,
            idempotency_key: str = Header(alias="Idempotency-Key", min_length=1, max_length=200),
            customer: SessionCustomer = Depends(require_customer)):
        customer_id = customer.commercial_customer_id or customer.id
        try:
            repo = make_repository()
            quote = repo.get_commercial_quote(quote_id, customer_id=customer_id)
            if quote is None:
                raise HTTPException(404, "Cotización no encontrada.")
            if quote["kind"] == "DIRECT_SALE":
                result = repo.accept_direct_sales_quote(quote_id=quote_id, customer_id=customer_id,
                    actor_user_id=customer.id, idempotency_key=idempotency_key)
                if result.get("error"):
                    raise HTTPException(409, result["error"])
            else:
                result = repo.accept_service_quote(quote_id=quote_id, customer_id=customer_id,
                    actor_user_id=customer.id)
            return {"quote": repo.get_commercial_quote(quote_id, customer_id=customer_id), **result}
        except HTTPException:
            raise
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        except SQLAlchemyError as exc:
            raise HTTPException(503, "No se pudo aceptar la cotización.") from exc

    @router.get("/api/customer/sales-orders")
    def customer_list_orders(customer: SessionCustomer = Depends(require_customer)):
        try:
            return {"items": make_repository().list_sales_orders(
                customer_id=customer.commercial_customer_id or customer.id)}
        except SQLAlchemyError as exc:
            raise HTTPException(503, "No se pudieron consultar tus ventas.") from exc

    @router.get("/api/customer/sales-orders/{order_id}")
    def customer_get_order(order_id: int, customer: SessionCustomer = Depends(require_customer)):
        try:
            row = make_repository().get_sales_order(
                order_id, customer_id=customer.commercial_customer_id or customer.id)
        except SQLAlchemyError as exc:
            raise HTTPException(503, "No se pudo cargar la venta.") from exc
        if row is None:
            raise HTTPException(404, "Venta no encontrada.")
        return row

    @router.get("/api/customer/payments")
    def customer_list_payments(status: str | None = None,
            limit: int = Query(default=50, ge=1, le=100), offset: int = Query(default=0, ge=0),
            customer: SessionCustomer = Depends(require_customer)):
        try:
            return {"items": make_repository().list_customer_payments(
                customer_id=customer.commercial_customer_id or customer.id,
                status=status, limit=limit, offset=offset)}
        except SQLAlchemyError as exc:
            raise HTTPException(503, "No se pudieron consultar tus pagos.") from exc

    @router.get("/api/admin/payments")
    def admin_list_payments(customer_id: int | None = Query(default=None, gt=0), status: str | None = None,
            limit: int = Query(default=50, ge=1, le=200), offset: int = Query(default=0, ge=0),
            _admin: SessionCustomer = Depends(require_admin)):
        try:
            return {"items": make_repository().list_admin_payments(
                customer_id=customer_id, status=status, limit=limit, offset=offset),
                "limit": limit, "offset": offset}
        except SQLAlchemyError as exc:
            raise HTTPException(503, "No se pudieron consultar los pagos.") from exc

    return router
