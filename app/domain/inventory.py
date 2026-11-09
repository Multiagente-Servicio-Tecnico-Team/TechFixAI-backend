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
    current_stock: int | None
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

    stock_value = values.get("current_stock")
    stock = None if stock_value is None else _validate_count(stock_value, "current_stock")
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


def validate_stock_count(value: object) -> int:
    return _validate_count(value, "counted_stock")


def validate_movement_reason(value: object) -> str:
    if not isinstance(value, str):
        raise InventoryValidationFailure("El motivo es obligatorio.", field="reason")
    reason = value.strip()
    if not 1 <= len(reason) <= 500:
        raise InventoryValidationFailure("El motivo debe tener entre 1 y 500 caracteres.", field="reason")
    return reason


def movement_type_for_delta(delta: object) -> str:
    """Map a non-zero stock delta to its manual movement kind."""
    if isinstance(delta, bool) or not isinstance(delta, int) or delta == 0:
        raise InventoryValidationFailure("El movimiento debe cambiar el saldo.", field="quantity_delta")
    return "ADJUSTMENT_IN" if delta > 0 else "ADJUSTMENT_OUT"


def validate_movement_sign(movement_type: object, delta: object, *, actor_kind: str = "USER") -> str:
    """Validate movement type/sign combinations at the domain boundary."""
    if movement_type == "OPENING_BALANCE" and actor_kind == "SYSTEM":
        if isinstance(delta, bool) or not isinstance(delta, int) or delta < 0:
            raise InventoryValidationFailure("El corte del sistema admite un saldo inicial no negativo.", field="quantity_delta")
        return "OPENING_BALANCE"
    expected = {
        "OPENING_BALANCE": lambda value: value > 0,
        "ADJUSTMENT_IN": lambda value: value > 0,
        "ADJUSTMENT_OUT": lambda value: value < 0,
        "PURCHASE_RECEIPT": lambda value: value > 0,
        "SALE": lambda value: value < 0,
    }
    if movement_type not in expected or actor_kind != "USER" or isinstance(delta, bool) or not isinstance(delta, int) or not expected[movement_type](delta):
        raise InventoryValidationFailure("El tipo de movimiento no coincide con el signo de la variación.", field="movement_type")
    return str(movement_type)


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
