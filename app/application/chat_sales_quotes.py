"""Shared persistence operations for customer-chat commercial quotations."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any


def save_chat_sales_quote(
    *,
    customer_id: int,
    quote_type: str,
    parts: list[dict[str, Any]],
    labor_cost: Decimal | str,
    observations: str,
    repository,
) -> dict[str, Any]:
    """Persist a pending direct-sale/PC_BUILD quote from verified catalog rows."""
    if type(customer_id) is not int or customer_id < 1:
        raise ValueError("Se requiere el cliente autenticado.")
    if quote_type not in {"DIRECT_SALE", "PC_BUILD"} or not parts:
        raise ValueError("La cotización comercial requiere tipo y artículos válidos.")

    lines: list[dict[str, int]] = []
    sources: dict[int, dict[str, Any]] = {}
    for part in parts:
        part_id = part.get("spare_part_id", part.get("inventory_id", part.get("id")))
        quantity = part.get("quantity")
        if type(part_id) is not int or part_id < 1 or type(quantity) is not int or quantity < 1:
            raise ValueError("Cada artículo requiere ID de inventario y cantidad positivos.")
        if part_id in sources:
            raise ValueError("Consolida las cantidades repetidas de un artículo.")
        sources[part_id] = part
        lines.append({"spare_part_id": part_id, "quantity": quantity})

    # El repositorio llega desde el adaptador que llama: la capa de aplicación no conoce la persistencia.
    saved = repository.create_direct_sales_quote(
        customer_id=customer_id,
        actor_user_id=None,
        lines=lines,
        expires_at=datetime.now(UTC) + timedelta(hours=24),
        observations=observations,
        origin="CHAT",
        quote_type=quote_type,
        labor_cost=str(labor_cost),
    )
    quote_id = saved.get("id")
    if type(quote_id) is not int or quote_id < 1:
        raise RuntimeError("No se pudo recuperar la cotización comercial creada.")

    persisted_parts = []
    for line in saved.get("lines", []):
        part_id = line.get("spare_part_id")
        source = sources.get(part_id)
        if source is None:
            raise RuntimeError("La cotización persistida contiene un artículo ajeno a la propuesta.")
        persisted_parts.append({
            **source,
            "id": part_id,
            "inventory_id": part_id,
            "name": line["name_snapshot"],
            "code": line["code_snapshot"],
            "quantity": int(line["quantity"]),
            "unit_price": Decimal(str(line["unit_price"])),
            "subtotal": Decimal(str(line["subtotal"])),
        })
    if len(persisted_parts) != len(sources):
        raise RuntimeError("La cotización persistida no coincide con sus artículos.")
    return {**saved, "id": quote_id, "parts": persisted_parts}
