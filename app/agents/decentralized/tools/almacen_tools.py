from langchain_core.tools import tool

from app.database.repository import lookup_inventory


@tool
def transferir_a_compras(motivo: str) -> str:
    """Deriva faltantes confirmados a Compras, sin crear pedidos."""
    if not isinstance(motivo, str) or not motivo.strip():
        raise ValueError("Motivo de transferencia obligatorio")
    return f"TRANSFERIR_COMPRAS: {motivo.strip()}"


@tool
def consultar_inventario(
    nombre_repuesto: str,
    cantidad: int = 1,
) -> dict[str, object]:
    """Consulta en PostgreSQL el stock y precio de un repuesto."""

    if not nombre_repuesto.strip():
        raise ValueError("El nombre del repuesto es obligatorio.")

    if cantidad < 1:
        raise ValueError("La cantidad debe ser mayor que cero.")

    result = lookup_inventory(
        requested_name=nombre_repuesto,
        quantity=cantidad,
    )

    return {
        **result,
        "unit_price": str(result["unit_price"]),
    }

@tool
def transferir_a_ventas(motivo: str) -> str:
    """Transfiere a Ventas los resultados del inventario."""
    return f"TRANSFERIR_VENTAS: {motivo}"
