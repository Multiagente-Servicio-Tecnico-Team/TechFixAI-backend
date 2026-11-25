from pathlib import Path
import re


SCHEMA = Path(__file__).parents[3] / "sql" / "esquema-vacio-produccion.sql"


def test_expanded_schema_contains_business_entities_and_refund_states():
    sql = SCHEMA.read_text(encoding="utf-8")
    required_tables = (
        "users", "tickets", "quotes", "quote_details", "spare_parts",
        "payments", "refunds", "warranties", "warranty_claims",
        "logistics_records", "suppliers", "purchase_orders", "purchase_order_items",
    )
    for table in required_tables:
        assert f"CREATE TABLE public.{table} (" in sql, table
    for label in ("REQUESTED", "APPROVED", "PROCESSED", "REJECTED"):
        assert f"'{label}'" in sql


def test_schema_contract_covers_refund_eligibility_and_quote_pricing_fields():
    sql = SCHEMA.read_text(encoding="utf-8")
    for column in (
        "customer_id", "payment_id", "ticket_id", "amount", "reason",
        "status", "total_amount", "unit_price", "current_stock",
    ):
        assert column in sql


def test_required_expanded_workflow_columns_and_enum_labels_are_present():
    sql = SCHEMA.read_text(encoding="utf-8")
    required = {
        "tickets": {"customer_id", "request_type", "diagnosis_type", "status"},
        "quotes": {"ticket_id", "quote_type", "labor_cost", "parts_cost", "total_amount", "status"},
        "payments": {"ticket_id", "quote_id", "customer_id", "payment_code", "amount", "status"},
        "refunds": {"payment_id", "ticket_id", "amount", "reason", "status", "processed_at"},
        "warranties": {"customer_id", "ticket_id", "quote_id", "warranty_code", "end_date", "status"},
        "warranty_claims": {"warranty_id", "ticket_id", "claim_code", "reason", "status"},
        "logistics_records": {"ticket_id", "mode", "status", "tracking_number", "scheduled_date"},
        "spare_parts": {"code", "unit_price", "current_stock", "active"},
    }
    for table, columns in required.items():
        block = re.search(rf"CREATE TABLE public\.{table} \((.*?)\n\);", sql, re.S)
        assert block, f"table {table} missing"
        for column in columns:
            assert re.search(rf"^\s*{column}\s", block.group(1), re.M), f"{table}.{column} missing"

    enums = {
        "ticket_status_enum": {"PAYMENT_PENDING", "CANCELLED"},
        "payment_status_enum": {"PENDING", "COMPLETED", "REFUNDED"},
        "refund_status_enum": {"REQUESTED", "APPROVED", "PROCESSED", "REJECTED"},
        "warranty_claim_status_enum": {"IN_REVIEW", "APPROVED_REPAIR", "APPROVED_REPLACEMENT", "APPROVED_REFUND", "REJECTED"},
        "logistics_mode_enum": {"PHYSICAL_STORE", "COURIER_SHIPMENT"},
        "logistics_status_enum": {"PENDING_RECEIPT", "RECEIVED_AT_WORKSHOP", "IN_TRANSIT", "DELIVERED"},
    }
    for enum, labels in enums.items():
        block = re.search(rf"CREATE TYPE public\.{enum} AS ENUM \((.*?)\);", sql, re.S)
        assert block, f"enum {enum} missing"
        found = set(re.findall(r"'([A-Z_]+)'", block.group(1)))
        assert labels <= found, f"{enum}: missing {labels - found}"
