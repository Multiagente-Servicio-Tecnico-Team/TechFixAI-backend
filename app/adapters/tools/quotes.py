"""Strict quote-calculation tool; amounts and identity stay server supplied."""

from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr

from app.application.catalog import CatalogService
from app.application.ports import CustomerContext
from app.application.quotes import calculate_quote
from app.adapters.tools.catalog import _require_customer


class QuotePartInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: StrictStr = Field(min_length=1, max_length=80)
    quantity: StrictInt = Field(ge=1, le=100)


class QuoteCalculationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    parts: list[QuotePartInput] = Field(default_factory=list, max_length=50)


def make_quote_calculation_tool(
    catalog: CatalogService,
    *,
    customer_context: CustomerContext,
    labor_task_type: Literal["maintenance", "diagnosis", "sale", "pc_build"],
    labor_cost: Decimal,
    quote_type: Literal["REPAIR", "DIRECT_SALE", "PC_BUILD"],
) -> StructuredTool:
    """Build a quote calculator with customer and financial policy bound by the server."""

    def calculate(parts: list[QuotePartInput]) -> dict[str, Any]:
        _require_customer(customer_context)
        validated_parts = []
        for requested in parts:
            item = catalog.find_by_code(requested.code.strip())
            if item is None:
                raise LookupError("No se encontro un producto activo con ese codigo.")
            try:
                stock = int(item["current_stock"])
                unit_price = Decimal(str(item["unit_price"]))
            except (KeyError, TypeError, ValueError, InvalidOperation) as exc:
                raise RuntimeError("El catalogo devolvio datos no validos.") from exc
            if stock < 0 or not unit_price.is_finite() or unit_price <= 0:
                raise RuntimeError("El catalogo devolvio datos no cotizables.")
            if stock < requested.quantity:
                raise ValueError("No hay stock suficiente para preparar la cotizacion.")
            validated_parts.append({
                **item,
                "quantity": requested.quantity,
                "unit_price": unit_price,
                "current_stock": stock,
            })
        quote = calculate_quote(
            labor_cost=labor_cost,
            labor_task_type=labor_task_type,
            parts=validated_parts,
        )
        return {"quote_type": quote_type, **quote}

    return StructuredTool.from_function(
        func=calculate,
        name="calcular_cotizacion",
        description=(
            "Calcula una propuesta con precios y stock vigentes del catalogo. "
            "El importe de mano de obra y la identidad del cliente se configuran "
            "en el servidor; aceptar esta propuesta requiere una confirmacion aparte."
        ),
        args_schema=QuoteCalculationInput,
    )
