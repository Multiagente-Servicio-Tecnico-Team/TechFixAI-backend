from pathlib import Path


MIGRATION = Path(__file__).resolve().parents[3] / "sql" / "migrations" / "014_purchase_orders_lifecycle.sql"


def test_purchase_order_migration_is_additive_and_has_legacy_preflight():
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    assert "begin;" in sql
    assert "commit;" in sql
    assert "purchase_order_audit_events" in sql
    assert "purchase_order_receipts" in sql
    assert "purchase_order_receipt_items" in sql
    assert "purchase_order_receipt_item_id" in sql
    assert "purchase_order_item_id" in sql
    assert "raise exception" in sql
    assert "drop table" not in sql
    assert "drop schema" not in sql


def test_purchase_order_schema_keeps_legacy_receipts_and_movement_origins():
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    assert "purchase_receipt_item_id" in sql
    assert "sales_order_item_id" in sql
    assert "num_nonnulls(purchase_receipt_item_id,purchase_order_receipt_item_id,sales_order_item_id) <= 1" in sql
    assert "uq_purchase_order_receipt_actor_key" in sql
    assert "uq_inventory_movements_purchase_order_receipt_item" in sql
    assert "on delete restrict" in sql


def test_purchase_order_migration_does_not_reinterpret_or_delete_existing_orders():
    sql = MIGRATION.read_text(encoding="utf-8").lower()
    assert "if exists (select 1 from public.purchase_orders)" in sql
    assert "classify and review existing purchase_orders" in sql
    assert "update public.purchase_orders" not in sql
    assert "update public.purchase_order_items" in sql
