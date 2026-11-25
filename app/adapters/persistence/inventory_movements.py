"""Regla transaccional compartida para cualquier variación de existencias."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import inspect, text
from app.domain.inventory import validate_movement_sign
from app.domain.errors import InventoryValidationFailure

MAX_STOCK = 999_999


def active_reserved_units(session: Any, part_id: int) -> int:
    if not inspect(session.connection()).has_table(
        "inventory_reservations",
        schema="public" if session.bind.dialect.name == "postgresql" else None,
    ):
        return 0
    return int(session.execute(text("""SELECT COALESCE(SUM(ri.quantity),0)
        FROM inventory_reservation_items ri
        JOIN inventory_reservations r ON r.id=ri.reservation_id
        WHERE ri.spare_part_id=:part AND r.status='RESERVED'
          AND r.expires_at>CURRENT_TIMESTAMP"""), {"part": part_id}).scalar_one())


def apply_stock_movement(
    session: Any,
    *,
    part_id: int,
    quantity_delta: int,
    movement_type: str,
    actor_user_id: int,
    reason: str | None = None,
    idempotency_key: str | None = None,
    request_hash: str | None = None,
    purchase_receipt_item_id: int | None = None,
    purchase_order_receipt_item_id: int | None = None,
    sales_order_item_id: int | None = None,
    code_snapshot: str | None = None,
    name_snapshot: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Actualiza saldo e inserta un movimiento; el caller posee la transacción."""
    lock = " FOR UPDATE" if session.bind.dialect.name == "postgresql" else ""
    part = session.execute(text("""SELECT id,code,name,current_stock
        FROM spare_parts WHERE id=:id""" + lock), {"id": part_id}).mappings().first()
    if part is None:
        raise ValueError("El repuesto ya no existe.")
    before = int(part["current_stock"])
    after = before + int(quantity_delta)
    purchase_origin_count = sum(origin is not None for origin in (
        purchase_receipt_item_id, purchase_order_receipt_item_id,
    ))
    try:
        validate_movement_sign(movement_type, int(quantity_delta))
    except InventoryValidationFailure as exc:
        raise ValueError(str(exc)) from exc
    if movement_type == "OPENING_BALANCE":
        if before != 0 or quantity_delta <= 0 or purchase_origin_count or sales_order_item_id:
            raise ValueError("El saldo inicial solo se registra una vez y debe ser positivo.")
    elif quantity_delta == 0:
        raise ValueError("El movimiento debe cambiar el saldo.")
    if movement_type in {"ADJUSTMENT_IN", "PURCHASE_RECEIPT"} and quantity_delta <= 0:
        raise ValueError("El movimiento de entrada requiere una cantidad positiva.")
    if movement_type in {"ADJUSTMENT_OUT", "SALE"} and quantity_delta >= 0:
        raise ValueError("El movimiento de salida requiere una cantidad negativa.")
    if movement_type == "PURCHASE_RECEIPT" and (purchase_origin_count != 1 or sales_order_item_id is not None):
        raise ValueError("La recepción debe referenciar exactamente una línea de recepción.")
    if movement_type == "SALE" and (sales_order_item_id is None or purchase_origin_count):
        raise ValueError("La venta debe referenciar solo su línea de pedido.")
    if movement_type in {"OPENING_BALANCE", "ADJUSTMENT_IN", "ADJUSTMENT_OUT"}:
        if purchase_origin_count or sales_order_item_id is not None:
            raise ValueError("El ajuste manual no puede tener origen de compra o venta.")
        if not reason or not reason.strip() or not idempotency_key or not request_hash:
            raise ValueError("El ajuste requiere motivo e idempotencia.")
    if after < 0 or after > MAX_STOCK:
        raise ValueError("El movimiento excede el rango de existencias permitido.")
    if movement_type in {"ADJUSTMENT_IN", "ADJUSTMENT_OUT", "SALE"}:
        reserved = active_reserved_units(session, part_id)
        if after < reserved:
            raise ValueError(f"El saldo no puede ser menor a las {reserved} unidades reservadas.")

    params = {"after": after, "part": part_id}
    if now is None:
        session.execute(text("UPDATE spare_parts SET current_stock=:after,updated_at=CURRENT_TIMESTAMP WHERE id=:part"), params)
    else:
        session.execute(text("UPDATE spare_parts SET current_stock=:after,updated_at=:now WHERE id=:part"), {**params, "now": now})
    row = session.execute(text("""INSERT INTO inventory_movements
        (spare_part_id,purchase_receipt_item_id,purchase_order_receipt_item_id,sales_order_item_id,movement_type,
         code_snapshot,name_snapshot,quantity_delta,stock_before,stock_after,
         actor_user_id,actor_kind,reason,idempotency_key,request_hash)
        VALUES (:part,:receipt_item,:order_receipt_item,:sales_item,:type,:code,:name,:delta,:before,:after,
                :actor,'USER',:reason,:key,:hash)
        RETURNING id,spare_part_id,code_snapshot,name_snapshot,movement_type,quantity_delta,
                  stock_before,stock_after,actor_user_id,actor_kind,reason,idempotency_key,created_at,
                  purchase_receipt_item_id,purchase_order_receipt_item_id,sales_order_item_id"""), {
        "part": part_id, "receipt_item": purchase_receipt_item_id,
        "order_receipt_item": purchase_order_receipt_item_id, "sales_item": sales_order_item_id,
        "type": movement_type, "code": code_snapshot or part["code"], "name": name_snapshot or part["name"],
        "delta": int(quantity_delta), "before": before, "after": after,
        "actor": actor_user_id, "reason": reason, "key": idempotency_key, "hash": request_hash,
    }).mappings().one()
    return dict(row)


def movement_to_dict(row: Any, *, actor_name: str | None = None, is_before_cutover: bool = False) -> dict[str, Any]:
    receipt_id = row.get("purchase_receipt_item_id")
    order_receipt_id = row.get("purchase_order_receipt_item_id")
    sales_id = row.get("sales_order_item_id")
    movement_type = str(row["movement_type"])
    source_type = "PURCHASE_ORDER_RECEIPT" if order_receipt_id is not None else (
        "PURCHASE_RECEIPT" if receipt_id is not None else "SALE" if sales_id is not None else (
        "OPENING_BALANCE" if movement_type == "OPENING_BALANCE" else "ADJUSTMENT"
        )
    )
    source_id = order_receipt_id if order_receipt_id is not None else receipt_id if receipt_id is not None else sales_id
    return {
        "id": int(row["id"]),
        "part_id": int(row["spare_part_id"]) if row.get("spare_part_id") is not None else None,
        "code_snapshot": str(row["code_snapshot"]),
        "name_snapshot": str(row["name_snapshot"]),
        "movement_type": movement_type,
        "quantity_delta": int(row["quantity_delta"]),
        "stock_before": int(row["stock_before"]),
        "stock_after": int(row["stock_after"]),
        "reason": row.get("reason"),
        "actor_kind": str(row.get("actor_kind") or "USER"),
        "actor_user_id": int(row["actor_user_id"]) if row.get("actor_user_id") is not None else None,
        "actor_name": actor_name or ("Sistema" if row.get("actor_kind") == "SYSTEM" else None),
        "created_at": row["created_at"].isoformat() if hasattr(row["created_at"], "isoformat") else str(row["created_at"]),
        "source_type": source_type,
        "source_id": int(source_id) if source_id is not None else None,
        "is_before_cutover": bool(is_before_cutover),
    }
