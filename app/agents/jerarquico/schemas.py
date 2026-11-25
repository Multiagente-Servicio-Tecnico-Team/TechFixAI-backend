from typing import Literal

from pydantic import BaseModel, Field, field_validator
from decimal import Decimal


class PartRequest(BaseModel):
    search_term: str = Field(min_length=1, max_length=100)
    quantity: int = Field(ge=1, le=1000)


class PendingCatalogRefinement(BaseModel):
    pending_index: int = Field(ge=0, le=9)
    constraints: str = Field(min_length=1, max_length=120)


class CatalogFollowupDecision(BaseModel):
    current_constraints: str | None = Field(default=None, max_length=200)
    pending_refinements: list[PendingCatalogRefinement] = Field(default_factory=list, max_length=10)
    additional_items: list[PartRequest] = Field(default_factory=list, max_length=10)
    cancel: bool = False


class IntakeDecision(BaseModel):
    route: Literal[
        "service",
        "sale",
        "pc_build",
        "warranty_status",
        "warranty_claim",
        "clarification",
        "informational",
    ]
    request_type: Literal[
        "REPAIR", "SUPPORT", "SALE", "PC_BUILD", "WARRANTY_CLAIM"
    ] | None = None
    title: str | None = Field(default=None, max_length=200)
    failure_description: str | None = Field(default=None, max_length=2000)
    clarification_question: str | None = Field(default=None, max_length=500)
    required_parts: list[PartRequest] = Field(default_factory=list, max_length=10)
    budget_max: Decimal | None = Field(default=None, gt=0, le=1000000)
    intended_use: str | None = Field(default=None, max_length=100)
    warranty_code: str | None = Field(default=None, max_length=50)
    informational_response: str | None = Field(
        default=None,
        max_length=4000,
        description=(
            "Campo legado: déjalo siempre null; el agente FAQ redacta la respuesta "
            "final para route informational."
        ),
    )

    @field_validator("required_parts", mode="before")
    @classmethod
    def normalize_required_parts(cls, value):
        return [] if value is None else value


class TechnicalDiagnosis(BaseModel):
    provisional_diagnosis: str = Field(min_length=1, max_length=2000)
    labor_task_type: Literal["maintenance", "diagnosis"] = Field(
        description=(
            "Usa diagnosis si la causa exacta no está identificada o el técnico "
            "debe inspeccionar el equipo antes de definir la reparación. Usa "
            "maintenance solo cuando el trabajo o cambio de componente ya está "
            "determinado."
        )
    )
    required_parts: list[PartRequest] = Field(default_factory=list, max_length=10)

    @field_validator("required_parts", mode="before")
    @classmethod
    def normalize_required_parts(cls, value):
        return [] if value is None else value


class QuoteConfirmation(BaseModel):
    decision: Literal["confirm", "decline", "modify", "unclear"]
    clarification_question: str | None = Field(default=None, max_length=500)
    modification_term: str | None = Field(default=None, max_length=100)
    replacement_category: Literal[
        "RAM Desktop",
        "RAM Laptop",
        "Almacenamiento",
        "Tarjeta de Video",
        "Procesador",
        "Placa Madre",
        "Fuente de Poder",
        "Gabinete",
    ] | None = None
