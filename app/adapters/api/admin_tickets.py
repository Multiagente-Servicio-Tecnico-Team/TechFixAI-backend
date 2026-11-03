"""Endpoints CRUD de tickets de taller, restringidos a usuarios ADMIN."""
from collections.abc import Callable
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.accounts.session import SessionCustomer
from app.database.repository import ServiceRepository

RequestType = Literal["REPAIR", "SALE", "PC_BUILD", "SUPPORT", "WARRANTY_CLAIM"]
DiagnosisType = Literal["HARDWARE", "SOFTWARE", "HYBRID", "NONE"]
TicketStatus = Literal[
    "NEW", "IN_DIAGNOSIS", "QUOTED", "PAYMENT_PENDING", "PAID", "IN_REPAIR",
    "READY_FOR_DELIVERY", "DELIVERED", "CANCELLED", "WARRANTY_IN_REVIEW",
]


class TicketCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer_email: str = Field(min_length=5, max_length=255)
    title: str = Field(min_length=2, max_length=200)
    failure_description: str = Field(min_length=1, max_length=10000)
    request_type: RequestType = "REPAIR"
    technician_id: int | None = Field(default=None, gt=0)
    diagnosis_type: DiagnosisType = "NONE"
    hardware_diagnosis: str | None = Field(default=None, max_length=10000)
    software_diagnosis: str | None = Field(default=None, max_length=10000)
    estimated_labor_hours: Decimal = Field(default=Decimal("0.0"), ge=0, le=999.9)
    is_remote_service: bool = False


class TicketPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    technician_id: int | None = Field(default=None, gt=0)
    title: str | None = Field(default=None, min_length=2, max_length=200)
    failure_description: str | None = Field(default=None, min_length=1, max_length=10000)
    request_type: RequestType | None = None
    diagnosis_type: DiagnosisType | None = None
    status: TicketStatus | None = None
    hardware_diagnosis: str | None = Field(default=None, max_length=10000)
    software_diagnosis: str | None = Field(default=None, max_length=10000)
    estimated_labor_hours: Decimal | None = Field(default=None, ge=0, le=999.9)
    is_remote_service: bool | None = None


def _ticket_out(row: dict[str, Any]) -> dict[str, Any]:
    result = dict(row)
    result["customer_name"] = " ".join(
        part for part in (result.pop("customer_first_name", ""), result.pop("customer_last_name", "")) if part
    )
    for name in ("quote_total", "payment_amount", "estimated_labor_hours"):
        value = result.get(name)
        if isinstance(value, Decimal):
            result[name] = format(value, "f")
    for name in ("created_at", "updated_at"):
        value = result.get(name)
        if isinstance(value, datetime):
            result[name] = value.isoformat()
    return result


def create_admin_ticket_router(
    *,
    require_admin: Callable[..., SessionCustomer],
    repository_factory: Callable[[], Any] | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/api/admin", tags=["administración de tickets"])
    make_repository = repository_factory or ServiceRepository

    @router.get("/customers")
    def customer_by_email(
        email: str = Query(min_length=5, max_length=255),
        _admin: SessionCustomer = Depends(require_admin),
    ):
        try:
            customer = make_repository().find_active_customer_by_email(email)
        except SQLAlchemyError as exc:
            raise HTTPException(status_code=503, detail="No se pudo consultar el cliente.") from exc
        if customer is None:
            raise HTTPException(status_code=404, detail="No se encontró un cliente activo con ese correo.")
        return {
            "id": customer["id"],
            "name": " ".join(part for part in (customer.get("name"), customer.get("last_name")) if part),
            "email": customer["email"],
            "phone": customer["phone"],
        }

    @router.get("/tickets")
    def list_tickets(
        status: TicketStatus | None = None,
        request_type: RequestType | None = None,
        search: str | None = Query(default=None, max_length=200),
        limit: int = Query(default=100, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
        _admin: SessionCustomer = Depends(require_admin),
    ):
        try:
            rows = make_repository().list_admin_tickets(
                status=status,
                request_type=request_type,
                search=search.strip() if search else None,
                limit=limit,
                offset=offset,
            )
        except SQLAlchemyError as exc:
            raise HTTPException(status_code=503, detail="No se pudieron cargar los tickets.") from exc
        return {"tickets": [_ticket_out(row) for row in rows], "limit": limit, "offset": offset}

    @router.get("/tickets/{ticket_id}")
    def get_ticket(ticket_id: int, _admin: SessionCustomer = Depends(require_admin)):
        try:
            row = make_repository().get_admin_ticket(ticket_id)
        except SQLAlchemyError as exc:
            raise HTTPException(status_code=503, detail="No se pudo cargar el ticket.") from exc
        if row is None:
            raise HTTPException(status_code=404, detail="Ticket no encontrado.")
        return _ticket_out(row)

    @router.post("/tickets", status_code=201)
    def create_ticket(body: TicketCreate, _admin: SessionCustomer = Depends(require_admin)):
        repository = make_repository()
        try:
            customer = repository.find_active_customer_by_email(body.customer_email)
            if customer is None:
                raise HTTPException(status_code=404, detail="El correo no corresponde a un cliente activo registrado.")
            values = body.model_dump(exclude={"customer_email"})
            values["customer_id"] = customer["id"]
            ticket_id = repository.create_admin_ticket(
                values=values,
                code=f"TCK-{uuid4().hex[:12].upper()}",
            )
            row = repository.get_admin_ticket(ticket_id)
        except HTTPException:
            raise
        except IntegrityError as exc:
            raise HTTPException(status_code=409, detail="Los datos del ticket no cumplen las relaciones del sistema.") from exc
        except SQLAlchemyError as exc:
            raise HTTPException(status_code=503, detail="No se pudo crear el ticket.") from exc
        return _ticket_out(row)

    @router.patch("/tickets/{ticket_id}")
    def update_ticket(
        ticket_id: int,
        body: TicketPatch,
        _admin: SessionCustomer = Depends(require_admin),
    ):
        values = body.model_dump(exclude_unset=True)
        required = {"title", "failure_description", "request_type", "diagnosis_type", "status", "estimated_labor_hours", "is_remote_service"}
        if any(name in values and values[name] is None for name in required):
            raise HTTPException(status_code=422, detail="Los campos requeridos del ticket no aceptan null.")
        try:
            repository = make_repository()
            if not repository.update_admin_ticket(ticket_id, values):
                raise HTTPException(status_code=404, detail="Ticket no encontrado.")
            row = repository.get_admin_ticket(ticket_id)
        except HTTPException:
            raise
        except IntegrityError as exc:
            raise HTTPException(status_code=409, detail="El técnico indicado no existe o no puede asignarse.") from exc
        except SQLAlchemyError as exc:
            raise HTTPException(status_code=503, detail="No se pudo actualizar el ticket.") from exc
        return _ticket_out(row)

    @router.delete("/tickets/{ticket_id}", status_code=204)
    def delete_ticket(ticket_id: int, _admin: SessionCustomer = Depends(require_admin)):
        try:
            deleted = make_repository().delete_admin_ticket(ticket_id)
        except IntegrityError as exc:
            raise HTTPException(status_code=409, detail="El ticket tiene registros relacionados que impiden eliminarlo.") from exc
        except SQLAlchemyError as exc:
            raise HTTPException(status_code=503, detail="No se pudo eliminar el ticket.") from exc
        if not deleted:
            raise HTTPException(status_code=404, detail="Ticket no encontrado.")
        return Response(status_code=204)

    return router
