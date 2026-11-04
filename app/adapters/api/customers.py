"""Admin routes for commercial customers; account authentication stays unchanged."""
from collections.abc import Callable
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.exc import SQLAlchemyError

from app.accounts.session import SessionCustomer
from app.adapters.persistence.customers import CustomerRepositoryAdapter
from app.application.customer_profiles import CustomerConflict, CustomerNotFound, CustomerProfileService


class CustomerWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    display_name: str = Field(min_length=2, max_length=200)
    phone: str = Field(min_length=7, max_length=30)
    email: str | None = Field(default=None, max_length=255)

    @field_validator("display_name", "phone")
    @classmethod
    def trim_nonempty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("El campo no puede estar vacío.")
        return value

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str | None) -> str | None:
        if value is not None and ("@" not in value or "." not in value.rsplit("@", 1)[-1]):
            raise ValueError("El correo no es válido.")
        return value.strip().casefold() if value is not None else None


class CustomerPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    display_name: str | None = Field(default=None, min_length=2, max_length=200)
    phone: str | None = Field(default=None, min_length=7, max_length=30)
    email: str | None = Field(default=None, max_length=255)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str | None) -> str | None:
        if value is not None and value and ("@" not in value or "." not in value.rsplit("@", 1)[-1]):
            raise ValueError("El correo no es válido.")
        return value.strip().casefold() if value else value


class LinkAccount(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: int = Field(gt=0)
    identity_verified: Literal[True]


def create_customer_router(
    *, require_admin: Callable[..., SessionCustomer], repository_factory: Callable[[], Any] | None = None
) -> APIRouter:
    router = APIRouter(prefix="/api/admin", tags=["clientes comerciales"])
    make_repository = repository_factory or CustomerRepositoryAdapter

    def service() -> CustomerProfileService:
        return CustomerProfileService(make_repository())

    @router.get("/customers")
    def list_customers(
        search: str | None = Query(default=None, max_length=200),
        email: str | None = Query(default=None, min_length=5, max_length=255),
        origin: Literal["MANUAL", "PORTAL"] | None = None,
        limit: int = Query(default=50, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
        _admin: SessionCustomer = Depends(require_admin),
    ):
        try:
            repository = make_repository()
            if email:
                rows = repository.list_customers(search=email.strip(), limit=2, offset=0)
                matches = [row for row in rows["items"] if (row.get("email") or "").casefold() == email.strip().casefold()]
                if not matches:
                    raise HTTPException(status_code=404, detail="No se encontró el cliente.")
                result = dict(matches[0])
                result["name"] = result["display_name"]
                return result
            rows = repository.list_customers(search=search.strip() if search else None, origin=origin, limit=limit, offset=offset)
            return {"items": rows["items"], "total": rows["total"], "limit": limit, "offset": offset}
        except HTTPException:
            raise
        except SQLAlchemyError as exc:
            raise HTTPException(status_code=503, detail="No se pudo consultar clientes.") from exc

    @router.post("/customers", status_code=201)
    def create_customer(body: CustomerWrite, admin: SessionCustomer = Depends(require_admin)):
        try:
            return service().create_manual(values=body.model_dump(), actor_id=admin.id)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except CustomerConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except SQLAlchemyError as exc:
            raise HTTPException(status_code=503, detail="No se pudo registrar el cliente.") from exc

    @router.get("/customers/{customer_id}")
    def get_customer(customer_id: int = Path(gt=0), _admin: SessionCustomer = Depends(require_admin)):
        try:
            result = service().get_customer(customer_id)
        except SQLAlchemyError as exc:
            raise HTTPException(status_code=503, detail="No se pudo consultar el cliente.") from exc
        if result is None:
            raise HTTPException(status_code=404, detail="Cliente no encontrado.")
        return result

    @router.patch("/customers/{customer_id}")
    def update_customer(customer_id: int, body: CustomerPatch, admin: SessionCustomer = Depends(require_admin)):
        values = body.model_dump(exclude_unset=True)
        if not values:
            raise HTTPException(status_code=422, detail="Envía al menos un campo para actualizar.")
        try:
            result = service().update_customer(customer_id=customer_id, values=values, actor_id=admin.id)
        except CustomerNotFound as exc:
            raise HTTPException(status_code=404, detail="Cliente no encontrado.") from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except SQLAlchemyError as exc:
            raise HTTPException(status_code=503, detail="No se pudo actualizar el cliente.") from exc
        return result

    @router.post("/customers/{customer_id}/link-account")
    def link_account(customer_id: int, body: LinkAccount, admin: SessionCustomer = Depends(require_admin)):
        try:
            return service().link_account(customer_id=customer_id, user_id=body.user_id,
                                          actor_id=admin.id, identity_verified=body.identity_verified)
        except CustomerNotFound as exc:
            raise HTTPException(status_code=404, detail="Cliente no encontrado.") from exc
        except CustomerConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except SQLAlchemyError as exc:
            raise HTTPException(status_code=503, detail="No se pudo vincular la cuenta.") from exc

    return router
