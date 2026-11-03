"""Strict LangChain tools for database-backed catalog operations."""

from typing import Any

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr

from app.application.catalog import CatalogService
from app.application.ports import CustomerContext


class CatalogLookupInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requested_name: StrictStr = Field(min_length=1, max_length=200)
    quantity: StrictInt = Field(default=1, ge=1, le=100)


def _require_customer(context: CustomerContext) -> None:
    if type(context.customer_id) is not int or context.customer_id < 1:
        raise PermissionError("Se requiere una sesiÃ³n de cliente autenticada.")


def make_catalog_lookup_tool(
    catalog: CatalogService,
    *,
    customer_context: CustomerContext,
) -> StructuredTool:
    """Build a catalog tool with authenticated context captured server-side."""

    def lookup(requested_name: str, quantity: int = 1) -> dict[str, Any]:
        _require_customer(customer_context)
        return catalog.lookup(requested_name, quantity)

    return StructuredTool.from_function(
        func=lookup,
        name="consultar_catalogo",
        description=(
            "Consulta en PostgreSQL el nombre, precio y stock actuales de un producto. "
            "No confirma compatibilidad ni reserva inventario."
        ),
        args_schema=CatalogLookupInput,
    )
