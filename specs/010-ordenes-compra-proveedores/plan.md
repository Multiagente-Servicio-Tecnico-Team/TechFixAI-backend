# Implementation Plan: Gestión de órdenes de compra a proveedores

**Branch**: `010-ordenes-compra-proveedores` | **Date**: 2026-11-09 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/010-ordenes-compra-proveedores/spec.md`

## Summary

Expose an ADMIN-only purchase-order lifecycle using the existing `purchase_orders` and `purchase_order_items` tables. Add a domain/application/API/persistence slice for draft, issue, cancel, search and detail. Add order-specific receipt records so stock can be received directly against an order before or after the supplier invoice. Each receipt and stock movement will commit atomically and idempotently. Supplier invoices remain separate and keep their optional header link to the order; the invoice receipt endpoint will not apply a second stock change for an order-linked invoice.

## Technical Context

**Language/Version**: Python 3.11+ syntax already used by the backend; use the repository's pinned `requirements.txt`.  
**Primary Dependencies**: FastAPI, Pydantic, SQLAlchemy Core, pg8000, PostgreSQL.  
**Storage**: PostgreSQL; current schema has `purchase_orders`, `purchase_order_items`, supplier purchase/receipt tables and `inventory_movements`.  
**Testing**: pytest; unit tests for domain rules, API contract/integration tests using isolated fixtures, and migration/schema contract tests.  
**Target Platform**: Existing FastAPI backend on Render and local development.  
**Project Type**: Backend web service.  
**Performance Goals**: Paginated order listing; order read/write operations should use bounded queries and indexed supplier/status/date filters. Receipt operations must serialize on the order and its lines.  
**Constraints**: No order action changes stock. Only a confirmed physical receipt does. Exact decimal money; ADMIN identity comes from the verified session. Existing records and the invoice-based receipt API must remain intact.  
**Scale/Scope**: One backend feature, PostgreSQL migration, API contracts, domain and repository behavior, documentation and tests; no frontend changes.

## Constitution Check

| Principle | Gate | Design response |
|---|---|---|
| Shared business rules | PASS | State transitions, quantity limits, totals and permissions live in domain/application rules; HTTP adapters only validate and translate. |
| Verified persistence | PASS | Session-derived ADMIN is the only actor. An LLM or payload cannot confirm receipt, stock, price or status. |
| Exact financial data | PASS | `Decimal` and PostgreSQL `NUMERIC`; server calculates order line and header totals. |
| Evidence and audit | PASS | Every issue, cancel and physical receipt records actor/time; cancellation requires reason. |
| Security/privacy | PASS | Reuse `require_admin`; no actor identity accepted from the request body; database errors remain redacted. |
| Traceable schema changes | PASS | One versioned additive migration; no destructive rebuild or drop of current purchase records. |
| Comparable tests | PASS | New purchase-order API contract tests cover the same permission, status and stock effects as the domain tests. |

**Pre-design gate**: PASS. No exception to the constitution is required.

## Project Structure

### Documentation (this feature)

```text
specs/010-ordenes-compra-proveedores/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── purchase-orders.openapi.yaml
└── tasks.md                  # produced by speckit-tasks, not this plan
```

### Source Code (repository root)

```text
app/
├── domain/purchase_orders.py
├── application/purchase_orders.py
├── adapters/
│   ├── api/purchase_orders.py
│   └── persistence/purchase_orders.py
└── infrastructure/chat_app.py       # router and repository wiring

sql/migrations/014_purchase_orders_lifecycle.sql
tests/
├── unit/domain/test_purchase_orders.py
├── integration/test_purchase_orders_api.py
├── integration/test_purchase_order_receipts.py
└── unit/infrastructure/test_purchase_orders_schema_contract.py
```

**Structure Decision**: Follow the existing `domain` / `application` / `adapters` / `infrastructure` separation and SQLAlchemy Core repository style used by `app/adapters/api/purchases.py`, `app/application/purchases.py`, and `app/adapters/persistence/purchases.py`. Register the new router in `app/infrastructure/chat_app.py` and extend the protected-path error mapping for `/api/admin/purchase-orders`.

## Phase 0: Research

Research decisions and evidence are recorded in [research.md](research.md). The material findings are:

1. Existing `purchase_orders` and `purchase_order_items` exist but have no API. They contain supplier, total, status, estimated arrival and basic line data; no order actor, issue/cancel audit, snapshots or lifecycle constraints are currently represented.
2. Existing `purchase_receipts` require a supplier purchase and each receipt line points to a supplier purchase line. That structure cannot represent receipt before invoice without changing the meaning of existing receipt rows.
3. Add separate order receipt header/line tables and a distinct origin reference on `inventory_movements`. Keep current invoice receipt rows and their API valid for purchases not linked to an order.
4. An invoice linked to an order is a financial document only; physical receipt is recorded through the order receipt API. Prevent the invoice receipt route from receiving the same order-linked purchase, avoiding duplicate stock changes.
5. Add optional supplier-invoice-line to order-line mapping so quantities invoiced can be shown separately from quantities received. Keep header `purchase_order_id` and supplier match validation.
6. The current schema snapshot shows the legacy order status default `PENDING`; new records start as `DRAFT`. Since that legacy state has no documented meaning, the migration does not silently translate populated orders. Its preflight aborts if legacy order rows need classification; the configured test database was observed with zero orders.

No unresolved business clarifications remain. Migration rollout will include a fail-fast preflight for legacy orders and linked supplier purchases that already have invoice-based receipts; those cases require explicit, non-destructive reconciliation before applying the migration.

## Phase 1: Design & Contracts

### Domain and persistence design

- `PurchaseOrderService` validates inputs, computes Decimal line/header totals, and applies allowed state transitions.
- `PurchaseOrderRepositoryAdapter` uses parameterized SQLAlchemy Core and explicit transactions. Lock the order and relevant lines while applying receipts; count already received units before committing.
- `PurchaseOrder` states: `DRAFT`, `ISSUED`, `PARTIALLY_RECEIVED`, `RECEIVED`, `CANCELLED`. Only DRAFT is editable. Cancellation preserves prior receipts and inventory movements.
- A physical receipt inserts order receipt header and lines, updates order status, inserts stock movements for catalog items, and appends audit events in one transaction. Free-text lines retain receipt evidence and do not affect inventory.
- `apply_stock_movement` gains an order-receipt source parameter and validates that each purchase movement has exactly one receipt-line origin (invoice receipt line or order receipt line). Movement read projections identify the originating order receipt.
- Idempotency key is unique per actor/order and stores a canonical request hash. Reusing the key with different content returns conflict.
- Invoice line `purchase_order_item_id` is nullable for compatibility and required only when the operator wants line-level invoiced quantity reconciliation. The reference must belong to the header-linked order. Existing invoice lines are not guessed or auto-merged.

### Migration design

Create `sql/migrations/014_purchase_orders_lifecycle.sql` as a transaction, after migration 013:

1. Extend `purchase_orders` with author/issue/cancel metadata, notes and currency; retain IDs, supplier FKs and totals. Extend order lines with code/description snapshots. Add checks/indexes for lifecycle values and common filters.
2. Set the default for new rows to `DRAFT`. The current test database was observed with zero order rows; migration 014 must preflight and abort before DDL on a non-empty installation until each legacy state has an explicitly reviewed mapping. Backfill line snapshots from current spare-part descriptions where possible or `custom_item_name` otherwise; keep snapshot nullable only for unrecoverable legacy rows.
3. Create `purchase_order_audit_events`, `purchase_order_receipts`, and `purchase_order_receipt_items` with actor/order/line FKs, idempotency uniqueness, positive-integer checks, timestamps and indexes. Change the order-line FK delete behavior from cascade to restrict after checking current references.
4. Add nullable `purchase_order_item_id` to `supplier_purchase_items` with restrictive FK and index. Existing invoice data remains valid and unmapped; do not infer line mappings from descriptions or matching names.
5. Add nullable `purchase_order_receipt_item_id` to `inventory_movements`; update source XOR and type/origin checks so an inventory purchase receipt references exactly one receipt item. Keep all existing movement references and rows unchanged.
6. Preflight linked invoices that already have invoice-based receipts. Abort before DDL if any exist; do not duplicate or silently remap these historical rows. Require an explicit reviewed mapping before migration is retried.
7. Rollback documentation may remove only new objects/columns after verifying they have no dependent data. Never cascade-drop existing purchase or stock history.

### API design

The new API uses [contracts/purchase-orders.openapi.yaml](contracts/purchase-orders.openapi.yaml). Existing invoice-line linkage and the prohibition on invoice-based receiving for order-linked purchases are documented in the adjusted [006 purchase contract](../../006-registro-compras-proveedores/contracts/purchases.openapi.yaml). All new routes are ADMIN-only and use the existing session cookie. Implement route handlers with the repository-factory injection pattern used by the purchases router. Keep invoice and order lifecycles separate while validating supplier and line relationships.

Purchase order quantities remain positive integers, matching the existing `purchase_order_items.quantity` column and integer stock. If current money columns are `NUMERIC(10,2)`, widen them to `NUMERIC(14,2)` in migration 014 without changing stored values. Existing order-line descriptions can be NULL only for legacy rows where both the linked spare part and custom name have disappeared; new API writes require a non-empty description and never invent a historical snapshot. `quantity_invoiced` is `0` when no invoice is linked, a decimal string when all linked invoice quantities are mapped, and `null` when any invoice quantity remains unreconciled.

### Constitution Check (post-design)

| Principle | Result | Evidence |
|---|---|---|
| Domain/application separation | PASS | State/totals in domain/application; FastAPI and SQL remain adapters. |
| Session-based actor | PASS | All writes pass `actor.id` from `require_admin`; no caller-supplied actor. |
| Exact money and stock | PASS | Decimal totals; stock changes only through transactional `apply_stock_movement`. |
| Audit and immutable history | PASS | Append-only order events and movements; canceled/received orders are not physically deleted. |
| Additive migration | PASS | Migration 014 adds support and preserves current records, subject to preflight for legacy linked receipts. |
| Contract parity | PASS | Tests are planned against OpenAPI and domain outcomes, including no stock change on order creation/issue. |

## Complexity Tracking

No constitution violations. Dedicated order-receipt tables are necessary to represent receipt before invoice while keeping current invoice receipts semantically stable and preventing a second stock effect.
