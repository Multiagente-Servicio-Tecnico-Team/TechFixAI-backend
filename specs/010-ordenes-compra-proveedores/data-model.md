# Data Model: Órdenes de compra a proveedores

Amounts use PEN and exact PostgreSQL `NUMERIC` / Python `Decimal`. Actor IDs are derived from the authenticated ADMIN session. This document describes the target model; migration 014 must preserve all existing identifiers and invoice receipts.

## Purchase order (`purchase_orders`)

| Field | Type / rule | Notes |
|---|---|---|
| `id` | BIGINT PK | Existing stable identifier |
| `supplier_id` | BIGINT FK `suppliers`, RESTRICT | Existing supplier relationship |
| `status` | `DRAFT`, `ISSUED`, `PARTIALLY_RECEIVED`, `RECEIVED`, `CANCELLED` | New rows default to DRAFT; legacy PENDING rows require reviewed classification before migration |
| `total_amount` | NUMERIC(14,2), >= 0 | Existing total; recalculated from lines in the backend |
| `currency` | CHAR(3), `PEN` | Explicit order currency |
| `estimated_arrival` | TIMESTAMPTZ nullable | Existing field |
| `notes` | TEXT nullable | Operational notes |
| `created_by_user_id` | BIGINT FK `users`, RESTRICT | Creator from ADMIN session |
| `issued_by_user_id`, `issued_at` | Nullable user FK / TIMESTAMPTZ | Set once when issued |
| `cancelled_by_user_id`, `cancelled_at`, `cancellation_reason` | Nullable actor/time/reason | Cancellation audit; preserves received quantities |
| `created_at`, `updated_at` | TIMESTAMPTZ | Existing timestamps and update trigger |

## Purchase order line (`purchase_order_items`)

| Field | Type / rule | Notes |
|---|---|---|
| `id` | BIGINT PK | Existing stable identifier |
| `purchase_order_id` | BIGINT FK, RESTRICT once referenced | Existing parent relationship; avoid deleting lines with receipt history |
| `spare_part_id` | BIGINT FK `spare_parts`, nullable, SET NULL | Existing optional inventory item |
| `code_snapshot` | VARCHAR(50) nullable | Catalog code captured at order time |
| `description_snapshot` | VARCHAR(300), nullable for legacy rows only | Backfilled from item name or `custom_item_name`; new API writes require a value |
| `custom_item_name` | Existing nullable text | Retain for compatibility; the snapshot is the stable API description |
| `quantity` | INTEGER > 0 | Existing schema uses integer quantities |
| `unit_cost`, `subtotal` | NUMERIC(14,2), non-negative | Existing exact values; backend recalculates subtotal |

## Order-specific receipt (`purchase_order_receipts`)

| Field | Type / rule | Notes |
|---|---|---|
| `id` | BIGINT PK | Receipt identity |
| `purchase_order_id` | BIGINT FK `purchase_orders`, RESTRICT | Required order origin |
| `actor_user_id` | BIGINT FK `users`, RESTRICT | ADMIN from session |
| `idempotency_key` | UUID, unique per order and actor | Prevents duplicate writes on retry |
| `request_hash` | CHAR(64), SHA-256 hex | Detects different payload under reused key |
| `received_at` | TIMESTAMPTZ | Confirmation time |
| `notes` | TEXT nullable | Receipt evidence |

## Order receipt line (`purchase_order_receipt_items`)

| Field | Type / rule | Notes |
|---|---|---|
| `id` | BIGINT PK | Stable receipt-line identity |
| `receipt_id` | BIGINT FK `purchase_order_receipts`, RESTRICT | Parent event |
| `purchase_order_item_id` | BIGINT FK `purchase_order_items`, RESTRICT | Must belong to receipt's order |
| `quantity_received` | INTEGER > 0 | Cumulative quantity cannot exceed ordered quantity |
| Movement reference | One-to-zero-or-one via `inventory_movements.purchase_order_receipt_item_id` | Only catalog lines have a movement; no redundant reverse FK is stored |

## Supplier invoice line linkage (`supplier_purchase_items`)

Add nullable `purchase_order_item_id` FK to `purchase_order_items`, RESTRICT, and an index. It is supplied only for an invoice linked at header to the same order and is validated to belong to that order. This supports reporting quantities invoiced without treating invoice creation as receipt or stock movement. Existing lines remain NULL; no historical mapping is inferred.

## Inventory movement provenance (`inventory_movements`)

Add nullable `purchase_order_receipt_item_id` FK, RESTRICT, unique when present. Keep current `purchase_receipt_item_id` and `sales_order_item_id`. Revise origin checks so `PURCHASE_RECEIPT` references exactly one of invoice receipt line or order receipt line; `SALE` continues referencing only a sales order line. The shared stock mutation adapter updates `spare_parts.current_stock` and inserts this ledger row in one transaction.

## Order audit (`purchase_order_audit_events`)

Append-only events with `id`, `purchase_order_id`, `actor_user_id`, `event_type`, `changed_fields` JSONB, and `created_at`. Events include `CREATED`, `UPDATED`, `ISSUED`, `CANCELLED`, `RECEIPT_CONFIRMED`, and `LEGACY_RECEIPT_RECONCILED`. Do not store credentials or unrestricted request payloads.

## Relationships and derived values

```text
suppliers 1 ── * purchase_orders 1 ── * purchase_order_items
purchase_orders 1 ── * purchase_order_receipts 1 ── * purchase_order_receipt_items
purchase_order_items 1 ── * purchase_order_receipt_items
purchase_order_items 0..1 ── * supplier_purchase_items
purchase_order_receipt_items 0..1 ── 1 inventory_movements ── 1 spare_parts
purchase_orders 1 ── * supplier_purchases (header purchase_order_id remains optional)
```

- `quantity_received` per order line is the sum of order receipt lines plus only explicitly reconciled legacy invoice receipt quantities.
- `quantity_pending = quantity_ordered - quantity_received` for non-cancelled lines; cancelled orders preserve received and show remaining as cancelled, not pending.
- `quantity_invoiced` is derived from supplier purchase lines with an explicit order-line link: `0` if no linked invoices exist, a decimal string if all linked invoice lines are mapped, and `null` if any linked invoice quantity remains unreconciled.
- Order creation, update, issue, invoice link and cancel do not change stock. A receipt adds stock only for `spare_part_id` lines.
- Before migration 014, abort safely if existing order rows or order-linked invoice receipts require interpretation/mapping; preserve them and require a reviewed explicit mapping before retrying the migration. No existing line is guessed from its name.
