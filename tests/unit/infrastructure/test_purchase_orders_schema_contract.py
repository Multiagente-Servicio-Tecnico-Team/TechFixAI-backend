from pathlib import Path


SCHEMA = Path(__file__).resolve().parents[3] / "sql" / "esquema-vacio-produccion.sql"


def _schema() -> str:
    return SCHEMA.read_text(encoding="utf-8").lower()


def test_schema_includes_purchase_order_lifecycle_tables():
    sql = _schema()
    for table in ("purchase_order_audit_events", "purchase_order_receipts", "purchase_order_receipt_items"):
        assert f"create table public.{table} (" in sql, table
    assert "purchase_order_receipt_item_id" in sql
    assert "purchase_order_item_id" in sql
    assert "drop table" not in sql
    assert "drop schema" not in sql


def test_purchase_order_schema_keeps_legacy_receipts_and_movement_origins():
    sql = _schema()
    assert "purchase_receipt_item_id" in sql
    assert "sales_order_item_id" in sql
    assert "num_nonnulls(purchase_receipt_item_id, purchase_order_receipt_item_id, sales_order_item_id) <= 1" in sql
    assert "uq_purchase_order_receipt_actor_key" in sql
    assert "uq_inventory_movements_purchase_order_receipt_item" in sql
    assert "on delete restrict" in sql
