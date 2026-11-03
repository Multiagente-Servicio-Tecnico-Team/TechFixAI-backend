"""Shared safe result for supplier purchases unsupported by the data model."""
from dataclasses import dataclass


@dataclass(frozen=True)
class ProcurementUnavailable:
    outcome: str
    message: str


def supplier_purchase_unavailable() -> ProcurementUnavailable:
    return ProcurementUnavailable(
        outcome="procurement_unavailable",
        message=(
            "La compra a proveedores no está disponible: el sistema no relaciona "
            "proveedores con productos ni registra cotizaciones de compra. No puedo "
            "confirmar proveedor, precio ni plazo. No se creó una orden ni se reservó "
            "inventario. Consulta las alternativas que sí estén disponibles en el catálogo."
        ),
    )
