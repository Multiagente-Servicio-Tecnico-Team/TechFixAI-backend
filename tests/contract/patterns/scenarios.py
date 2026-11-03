"""Escenarios equivalentes para comparar las tres topologías."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Scenario:
    id: str
    prompt: str
    expected_writes: tuple[str, ...]


SCENARIOS = (
    Scenario("catalog.exact", "Consulta disponibilidad de SSD NVMe 512GB", ()),
    Scenario("quote.accept", "Acepto la cotización mostrada", ("quote", "payment_pending")),
    Scenario("refund.pending", "Solicito un reembolso de un pago completado", ("refund_requested",)),
    Scenario("supplier.unavailable", "Compra al proveedor un repuesto agotado", ()),
    Scenario("knowledge.demo_faq", "¿Cuál es la dirección de la tienda?", ()),
)
