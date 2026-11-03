from langchain_core.tools import tool

from app.application.catalog import CatalogService
from app.database.repository import ServiceRepository

catalog_service = CatalogService(ServiceRepository())


@tool
def consultar_inventario(nombre_repuesto: str, cantidad: int = 1) -> dict[str, object]:
    """Consulta existencias y precio actual de un repuesto en PostgreSQL."""
    return catalog_service.lookup(nombre_repuesto, cantidad)
