from datetime import datetime, timezone

import pytest

from app.adapters.persistence.inventory_movements import apply_stock_movement, movement_to_dict


class _Result:
    def __init__(self, row=None):
        self.row = row

    def mappings(self):
        return self

    def first(self):
        return self.row

    def one(self):
        return self.row


class _Session:
    bind = type("Bind", (), {"dialect": type("Dialect", (), {"name": "sqlite"})()})()

    def __init__(self):
        self.stock = 3
        self.inserted = None

    def execute(self, statement, params=None):
        sql = str(statement)
        params = params or {}
        if sql.startswith("SELECT id,code,name,current_stock"):
            return _Result({"id": params["id"], "code": "RAM-1", "name": "RAM", "current_stock": self.stock})
        if sql.startswith("UPDATE spare_parts"):
            self.stock = params["after"]
            return _Result()
        if sql.startswith("INSERT INTO inventory_movements"):
            self.inserted = dict(params)
            return _Result({
                "id": 19,
                "spare_part_id": params["part"],
                "code_snapshot": params["code"],
                "name_snapshot": params["name"],
                "movement_type": params["type"],
                "quantity_delta": params["delta"],
                "stock_before": params["before"],
                "stock_after": params["after"],
                "actor_user_id": params["actor"],
                "actor_kind": "USER",
                "reason": params["reason"],
                "idempotency_key": params["key"],
                "created_at": datetime.now(timezone.utc),
                "purchase_receipt_item_id": params["receipt_item"],
                "purchase_order_receipt_item_id": params["order_receipt_item"],
                "sales_order_item_id": params["sales_item"],
            })
        raise AssertionError(f"Unexpected SQL: {sql}")


def test_apply_stock_movement_accepts_order_receipt_origin():
    session = _Session()
    movement = apply_stock_movement(
        session,
        part_id=5,
        quantity_delta=2,
        movement_type="PURCHASE_RECEIPT",
        actor_user_id=8,
        purchase_order_receipt_item_id=21,
    )
    assert session.stock == 5
    assert session.inserted["order_receipt_item"] == 21
    assert session.inserted["receipt_item"] is None
    assert movement["purchase_order_receipt_item_id"] == 21


@pytest.mark.parametrize(
    "origins",
    [
        {},
        {"purchase_receipt_item_id": 4, "purchase_order_receipt_item_id": 21},
        {"purchase_order_receipt_item_id": 21, "sales_order_item_id": 9},
    ],
)
def test_purchase_movement_requires_exactly_one_receipt_origin(origins):
    session = _Session()
    with pytest.raises(ValueError, match="referenciar exactamente una línea de recepción"):
        apply_stock_movement(
            session,
            part_id=5,
            quantity_delta=1,
            movement_type="PURCHASE_RECEIPT",
            actor_user_id=8,
            **origins,
        )
    assert session.stock == 3


def test_movement_projection_identifies_purchase_order_receipt_source():
    payload = movement_to_dict({
        "id": 2,
        "spare_part_id": 5,
        "code_snapshot": "RAM-1",
        "name_snapshot": "RAM",
        "movement_type": "PURCHASE_RECEIPT",
        "quantity_delta": 1,
        "stock_before": 3,
        "stock_after": 4,
        "actor_user_id": 8,
        "actor_kind": "USER",
        "reason": None,
        "idempotency_key": None,
        "created_at": datetime.now(timezone.utc),
        "purchase_receipt_item_id": None,
        "purchase_order_receipt_item_id": 21,
        "sales_order_item_id": None,
    })
    assert payload["source_type"] == "PURCHASE_ORDER_RECEIPT"
    assert payload["source_id"] == 21
