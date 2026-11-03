from decimal import Decimal, InvalidOperation
from typing import Any, Callable

from app.application.ports import CatalogReader


CatalogLookup = Callable[[str, int], dict[str, Any]]


def lookup_catalog_item(
    requested_name: str,
    quantity: int = 1,
    *,
    lookup: CatalogLookup,
) -> dict[str, Any]:
    """Validate tool input and return only database-backed catalog values."""
    if not isinstance(requested_name, str) or not requested_name.strip():
        raise ValueError("El nombre del artículo es obligatorio.")
    if type(quantity) is not int or quantity < 1 or quantity > 100:
        raise ValueError("La cantidad debe ser un entero entre 1 y 100.")
    result = lookup(requested_name.strip(), quantity)
    if type(result.get("stock")) is not int or result["stock"] < 0:
        raise RuntimeError("El repositorio devolvió una cantidad de inventario no válida.")
    if type(result.get("available")) is not bool:
        raise RuntimeError("El repositorio no confirmó la disponibilidad.")
    if result["available"] != (result["stock"] >= quantity):
        raise RuntimeError("El repositorio devolvió disponibilidad inconsistente.")
    try:
        unit_price = Decimal(str(result["unit_price"]))
    except (InvalidOperation, TypeError) as exc:
        raise RuntimeError("El repositorio devolvió un precio no válido.") from exc
    if not unit_price.is_finite() or unit_price < 0:
        raise RuntimeError("El repositorio devolvió un precio no permitido.")
    if result.get("found", True) and result["available"] and unit_price <= 0:
        raise RuntimeError("El repositorio devolvió un precio no permitido.")
    result["unit_price"] = str(unit_price.quantize(Decimal("0.01")))
    return result


class CatalogService:
    """Shared catalog use case over an injected repository port."""

    def __init__(self, repository: CatalogReader) -> None:
        self._repository = repository

    def lookup(self, requested_name: str, quantity: int = 1) -> dict[str, Any]:
        return lookup_catalog_item(
            requested_name,
            quantity,
            lookup=self._repository.lookup_inventory,
        )

    def find_spare_parts(self, search_term: str) -> list[dict[str, Any]]:
        return self._repository.find_spare_parts(search_term)

    def find_catalog_items(
        self, search_term: str, *, limit: int = 20
    ) -> list[dict[str, Any]]:
        return self._repository.find_catalog_items(search_term, limit=limit)

    def find_by_code(self, code: str) -> dict[str, Any] | None:
        return self._repository.find_spare_part_by_code(code)

    def find_alternatives(self, search_term: str) -> list[dict[str, Any]]:
        return self._repository.find_spare_part_alternatives(search_term)
