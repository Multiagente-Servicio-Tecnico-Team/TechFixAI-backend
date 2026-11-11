"""Catálogo común de capacidades y políticas de rol.

Los identificadores son etiquetas de aplicación, nunca nombres SQL ejecutables.
"""
from dataclasses import dataclass
from typing import Literal

from app.domain.principal import Principal


OperationKind = Literal["read", "write"]


@dataclass(frozen=True)
class Capability:
    name: str
    operation: OperationKind
    roles: frozenset[str]
    description: str


CAPABILITIES = {
    item.name: item
    for item in (
        Capability("customer.chat", "read", frozenset({"CUSTOMER"}), "Atención autenticada del cliente."),
        Capability("admin.customers", "read", frozenset({"ADMIN"}), "Consulta de clientes comerciales."),
        Capability("admin.tickets", "read", frozenset({"ADMIN"}), "Consulta de tickets de servicio."),
        Capability("admin.inventory", "read", frozenset({"ADMIN"}), "Consulta de inventario."),
        Capability("admin.suppliers", "read", frozenset({"ADMIN"}), "Consulta de proveedores."),
        Capability("admin.purchases", "read", frozenset({"ADMIN"}), "Consulta de compras a proveedores."),
        Capability("admin.purchase_orders", "read", frozenset({"ADMIN"}), "Consulta de órdenes de compra."),
        Capability("admin.sales", "read", frozenset({"ADMIN"}), "Consulta de cotizaciones, pagos y ventas."),
        Capability("admin.accounting", "read", frozenset({"ADMIN"}), "Consulta contable interna."),
        Capability("admin.write", "write", frozenset({"ADMIN"}), "Escrituras administrativas sujetas a confirmación."),
    )
}


class CapabilityError(Exception):
    def __init__(self, code: str, detail: str, status: int = 422):
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.status = status


def require_capability(principal: Principal, capability_name: str) -> Capability:
    capability = CAPABILITIES.get(capability_name)
    if capability is None:
        raise CapabilityError("unsupported", "Esa operación no está disponible.", 422)
    if principal.role not in capability.roles:
        raise CapabilityError("forbidden", "Tu sesión no permite esa operación.", 403)
    return capability
