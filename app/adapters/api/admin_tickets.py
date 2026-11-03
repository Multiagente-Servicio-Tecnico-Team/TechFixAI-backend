"""Endpoints CRUD de tickets de taller, restringidos a usuarios ADMIN."""
from collections.abc import Callable
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.accounts.session import SessionCustomer
from app.adapters.persistence.admin_tickets import AdminTicketRepositoryAdapter
from app.application.admin_tickets import AdminTicketService
from app.domain.ticket_management import ADVANCE_METHODS, money

RequestType = Literal["REPAIR", "SALE", "PC_BUILD", "SUPPORT", "WARRANTY_CLAIM"]
DiagnosisType = Literal["HARDWARE", "SOFTWARE", "HYBRID", "NONE"]
TicketStatus = Literal[
    "NEW", "IN_DIAGNOSIS", "QUOTED", "PAYMENT_PENDING", "PAID", "IN_REPAIR",
    "READY_FOR_DELIVERY", "DELIVERED", "CANCELLED", "WARRANTY_IN_REVIEW",
]


class TicketCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contact_name: str = Field(min_length=3, max_length=200)
    contact_phone: str = Field(min_length=9, max_length=20)
    contact_email: str | None = Field(default=None, min_length=5, max_length=255)
    title: str = Field(min_length=2, max_length=200)
    failure_description: str = Field(min_length=5, max_length=10000)
    request_type: RequestType = "REPAIR"
    advance_amount: Decimal | None = Field(default=None, gt=0, max_digits=10, decimal_places=2)
    advance_payment_method: str | None = None
    technician_id: int | None = Field(default=None, gt=0)
    diagnosis_type: DiagnosisType = "NONE"
    hardware_diagnosis: str | None = Field(default=None, max_length=10000)
    software_diagnosis: str | None = Field(default=None, max_length=10000)
    estimated_labor_hours: Decimal = Field(default=Decimal("0.0"), ge=0, le=999.9)
    is_remote_service: bool = False

    @field_validator("contact_email")
    @classmethod
    def validate_contact_email(cls, value):
        if value is not None and ("@" not in value or "." not in value.rsplit("@", 1)[-1]):
            raise ValueError("El correo de contacto no es válido.")
        return value


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
    contact_name: str | None = Field(default=None, min_length=3, max_length=200)
    contact_phone: str | None = Field(default=None, min_length=9, max_length=20)
    contact_email: str | None = Field(default=None, max_length=255)
    advance_amount: Decimal | None = Field(default=None, gt=0, max_digits=10, decimal_places=2)
    advance_payment_method: str | None = None


class QuotePart(BaseModel):
    model_config = ConfigDict(extra="forbid")
    spare_part_id: int = Field(gt=0)
    quantity: int = Field(ge=1, le=1000)


class TicketQuoteCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    quote_type: Literal["REPAIR", "DIRECT_SALE", "PC_BUILD"]
    labor_task_type: Literal["maintenance", "diagnosis", "sale", "pc_build"]
    parts: list[QuotePart] = Field(max_length=50)
    observations: str | None = Field(default=None, max_length=2000)

    @field_validator("labor_task_type")
    @classmethod
    def match_quote_type(cls, value, info):
        quote_type = info.data.get("quote_type")
        compatible = {"REPAIR": {"maintenance", "diagnosis"}, "DIRECT_SALE": {"sale"}, "PC_BUILD": {"pc_build"}}
        if quote_type and value not in compatible[quote_type]:
            raise ValueError("El tipo de mano de obra no corresponde a la cotización.")
        return value


def _ticket_out(row: dict[str, Any]) -> dict[str, Any]:
    result = dict(row)
    result["customer_name"] = " ".join(
        part for part in (result.pop("customer_first_name", ""), result.pop("customer_last_name", "")) if part
    )
    result["contact_name"] = result.get("contact_name") or result.get("customer_name")
    if result.get("quote_id") is not None:
        result["quote"] = {
            "id": result.pop("quote_id"), "ticket_id": result["id"],
            "quote_type": result.pop("quote_type"), "labor_cost": result.pop("quote_labor_cost"),
            "parts_cost": result.pop("quote_parts_cost"), "total_amount": result.get("quote_total"),
            "status": result.get("quote_status"), "observations": result.pop("quote_observations"),
            "created_at": result.pop("quote_created_at"),
        }
    else:
        for key in ("quote_id", "quote_type", "quote_labor_cost", "quote_parts_cost", "quote_observations", "quote_created_at"):
            result.pop(key, None)
        result["quote"] = None
    for name in ("quote_total", "payment_amount", "estimated_labor_hours", "advance_amount"):
        value = result.get(name)
        if isinstance(value, Decimal):
            result[name] = format(value, "f")
    if result.get("quote"):
        for name in ("labor_cost", "parts_cost", "total_amount"):
            value = result["quote"].get(name)
            if isinstance(value, Decimal):
                result["quote"][name] = format(value, ".2f")
    for name in ("created_at", "updated_at"):
        value = result.get(name)
        if isinstance(value, datetime):
            result[name] = value.isoformat()
    if result.get("quote") and isinstance(result["quote"].get("created_at"), datetime):
        result["quote"]["created_at"] = result["quote"]["created_at"].isoformat()
    return result


def create_admin_ticket_router(
    *,
    require_admin: Callable[..., SessionCustomer],
    repository_factory: Callable[[], Any] | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/api/admin", tags=["administración de tickets"])
    make_repository = repository_factory or AdminTicketRepositoryAdapter
    make_service = lambda: AdminTicketService(make_repository())

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
        origin: Literal["MANUAL", "ONLINE"] | None = None,
        limit: int = Query(default=50, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
        _admin: SessionCustomer = Depends(require_admin),
    ):
        try:
            rows = make_service().list_tickets(
                status=status,
                request_type=request_type,
                origin=origin,
                search=search.strip() if search else None,
                limit=limit,
                offset=offset,
            )
        except SQLAlchemyError as exc:
            raise HTTPException(status_code=503, detail="No se pudieron cargar los tickets.") from exc
        return {"items": [_ticket_out(row) for row in rows["items"]], "total": rows["total"], "limit": limit, "offset": offset}

    @router.get("/tickets/{ticket_id}")
    def get_ticket(ticket_id: int, _admin: SessionCustomer = Depends(require_admin)):
        try:
            service = make_service()
            row = service.get_ticket(ticket_id)
        except SQLAlchemyError as exc:
            raise HTTPException(status_code=503, detail="No se pudo cargar el ticket.") from exc
        if row is None:
            raise HTTPException(status_code=404, detail="Ticket no encontrado.")
        row["audit_events"] = service.audit_events(ticket_id)
        return _ticket_out(row)

    @router.post("/tickets", status_code=201)
    def create_ticket(body: TicketCreate, _admin: SessionCustomer = Depends(require_admin)):
        if body.advance_amount is not None and body.advance_payment_method not in ADVANCE_METHODS:
            raise HTTPException(status_code=422, detail="El adelanto requiere un método válido.")
        if body.advance_amount is None and body.advance_payment_method is not None:
            raise HTTPException(status_code=422, detail="No envíe método de adelanto sin importe.")
        service = make_service()
        repository = service.repository
        try:
            values = body.model_dump()
            values.update(customer_id=None, origin="MANUAL", diagnosis_type="NONE", status="NEW", technician_id=None, estimated_labor_hours=Decimal("0.0"), is_remote_service=False, hardware_diagnosis=None, software_diagnosis=None)
            ticket_id = service.create_manual_ticket(
                values=values,
                code=f"TCK-{uuid4().hex[:12].upper()}",
                actor_id=_admin.id,
            )
            row = service.get_ticket(ticket_id)
            row["audit_events"] = service.audit_events(ticket_id)
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
        if "advance_payment_method" in values and values["advance_payment_method"] is not None and values["advance_payment_method"] not in ADVANCE_METHODS:
            raise HTTPException(status_code=422, detail="Método de adelanto inválido.")
        if any(name in values and values[name] is None for name in ("contact_name", "contact_phone")):
            raise HTTPException(status_code=422, detail="El nombre y teléfono de contacto no aceptan null.")
        required = {"title", "failure_description", "request_type", "diagnosis_type", "status", "estimated_labor_hours", "is_remote_service"}
        if any(name in values and values[name] is None for name in required):
            raise HTTPException(status_code=422, detail="Los campos requeridos del ticket no aceptan null.")
        try:
            service = make_service()
            current = service.get_ticket(ticket_id)
            if current is None:
                raise HTTPException(status_code=404, detail="Ticket no encontrado.")
            advance_amount = values.get("advance_amount", current.get("advance_amount"))
            advance_method = values.get("advance_payment_method", current.get("advance_payment_method"))
            if (advance_amount is None) != (advance_method is None):
                raise HTTPException(status_code=422, detail="El importe y método del adelanto deben informarse o quitarse juntos.")
            if current.get("origin") == "MANUAL":
                for name in ("contact_name", "contact_phone"):
                    if values.get(name, current.get(name)) is None:
                        raise HTTPException(status_code=422, detail="Un ticket manual requiere nombre y teléfono de contacto.")
            if not service.update_ticket(ticket_id=ticket_id, values=values, actor_id=_admin.id):
                raise HTTPException(status_code=404, detail="Ticket no encontrado.")
            row = service.get_ticket(ticket_id)
            row["audit_events"] = service.audit_events(ticket_id)
        except HTTPException:
            raise
        except IntegrityError as exc:
            raise HTTPException(status_code=409, detail="El técnico indicado no existe o no puede asignarse.") from exc
        except SQLAlchemyError as exc:
            raise HTTPException(status_code=503, detail="No se pudo actualizar el ticket.") from exc
        return _ticket_out(row)

    @router.post("/tickets/{ticket_id}/quotes", status_code=201)
    def create_quote(ticket_id: int, body: TicketQuoteCreate, _admin: SessionCustomer = Depends(require_admin)):
        from app.settings import load_settings
        task_types = {"maintenance": "maintenance", "diagnosis": "diagnosis", "sale": "sale", "pc_build": "pc_build"}
        try:
            settings = load_settings()
            result = make_service().create_quote(
                ticket_id=ticket_id, actor_id=_admin.id, quote_type=body.quote_type,
                labor_task_type=body.labor_task_type,
                labor_cost=settings.labor_price_for(task_types[body.labor_task_type]),
                parts=[part.model_dump() for part in body.parts], observations=body.observations,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except SQLAlchemyError as exc:
            raise HTTPException(status_code=503, detail="No se pudo crear la cotización.") from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail="La configuración de cotizaciones no está disponible.") from exc
        if result is None:
            raise HTTPException(status_code=404, detail="Ticket no encontrado.")
        return {key: format(value, ".2f") if isinstance(value, Decimal) else value for key, value in result.items()}

    @router.delete("/tickets/{ticket_id}", status_code=204)
    def delete_ticket(ticket_id: int, _admin: SessionCustomer = Depends(require_admin)):
        try:
            exists = make_service().get_ticket(ticket_id)
        except SQLAlchemyError as exc:
            raise HTTPException(status_code=503, detail="No se pudo consultar el ticket.") from exc
        if not exists:
            raise HTTPException(status_code=404, detail="Ticket no encontrado.")
        raise HTTPException(status_code=409, detail="El borrado físico está deshabilitado. Cambie el estado a CANCELLED.")

    return router
