"""Tipos y reglas del catálogo operativo de repuestos."""
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
import re
from typing import Mapping

from app.domain.errors import InventoryValidationFailure

CODE_PATTERN = re.compile(r"^[A-Z0-9]+(?:-[A-Z0-9]+)*$")
PRICE_PATTERN = re.compile(r"^(0|[1-9][0-9]{0,7})\.[0-9]{2}$")
MAX_STOCK = 999_999


@dataclass(frozen=True)
class InventoryPartDraft:
    code: str
    name: str
    category: str
    description: str | None
    unit_price: Decimal
    current_stock: int
    minimum_threshold: int


@dataclass(frozen=True)
class InventoryPart:
    id: int
    code: str
    name: str
    category: str | None
    description: str | None
    unit_price: Decimal
    current_stock: int
    minimum_threshold: int
    active: bool
    created_at: datetime | str
    updated_at: datetime | str


def validate_inventory_part(values: Mapping[str, object]) -> InventoryPartDraft:
    """Valida un alta/reemplazo sin convertir dinero a float ni normalizar la categoría."""
    code = values.get("code")
    if not isinstance(code, str) or len(code) < 1 or len(code) > 50 or not CODE_PATTERN.fullmatch(code):
        raise InventoryValidationFailure(
            "Usa de 1 a 50 caracteres: letras mayúsculas, números y guiones.",
            field="code",
        )

    raw_name = values.get("name")
    name = raw_name.strip() if isinstance(raw_name, str) else ""
    if not 3 <= len(name) <= 150:
        raise InventoryValidationFailure("El nombre debe tener entre 3 y 150 caracteres.", field="name")

    category = values.get("category")
    if not isinstance(category, str) or not category.strip() or len(category) > 50:
        raise InventoryValidationFailure("La categoría es obligatoria y admite hasta 50 caracteres.", field="category")

    description = values.get("description")
    if description is not None and not isinstance(description, str):
        raise InventoryValidationFailure("La descripción debe ser texto.", field="description")

    raw_price = values.get("unit_price")
    if not isinstance(raw_price, str) or not PRICE_PATTERN.fullmatch(raw_price):
        raise InventoryValidationFailure("El precio debe ser un importe decimal de dos posiciones.", field="unit_price")
    try:
        price = Decimal(raw_price)
    except InvalidOperation as exc:
        raise InventoryValidationFailure("El precio no es válido.", field="unit_price") from exc
    if not price.is_finite() or price <= 0:
        raise InventoryValidationFailure("El precio debe ser mayor que cero.", field="unit_price")

    stock = _validate_count(values.get("current_stock"), "current_stock")
    threshold = _validate_count(values.get("minimum_threshold"), "minimum_threshold")
    return InventoryPartDraft(
        code=code,
        name=name,
        category=category,
        description=description,
        unit_price=price,
        current_stock=stock,
        minimum_threshold=threshold,
    )


def _validate_count(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= MAX_STOCK:
        raise InventoryValidationFailure("La cantidad debe ser un entero entre 0 y 999999.", field=field)
    return value


def part_to_dict(part: InventoryPart) -> dict[str, object]:
    """Proyección estable para la respuesta JSON."""
    result: dict[str, object] = {
        "id": part.id,
        "code": part.code,
        "name": part.name,
        "category": part.category,
        "description": part.description,
        "unit_price": format(part.unit_price, ".2f"),
        "current_stock": part.current_stock,
        "minimum_threshold": part.minimum_threshold,
        "active": part.active,
        "created_at": _iso(part.created_at),
        "updated_at": _iso(part.updated_at),
    }
    return result


def _iso(value: datetime | str) -> str:
    return value.isoformat() if isinstance(value, datetime) else str(value)
