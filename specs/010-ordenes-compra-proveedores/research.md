# Research: Órdenes de compra a proveedores

## Decisions

### Keep order, invoice and physical receipt separate

- **Decision**: Keep `purchase_orders` as the supplier request and `supplier_purchases` as received financial documents. Record receipt-before-invoice and receipt-after-invoice through order-specific receipt headers and lines.
- **Rationale**: Existing `purchase_receipts.purchase_id` is required and its items reference invoice lines. Making those existing rows polymorphic would change their meaning and increase risk to history. Separate order receipt tables preserve the established invoice flow.
- **Alternatives considered**: Make existing receipt source columns nullable and polymorphic; rejected for this feature because it forces changes to constraints and reads of existing invoice receipt data. Reuse invoice receipts and require an invoice before receiving; rejected because the user explicitly wants receipt before invoice.
- **Evidence**: `sql/esquema-vacio-produccion.sql` defines `purchase_receipts.purchase_id NOT NULL` referencing `supplier_purchases`; `purchase_receipt_items.purchase_item_id` references supplier invoice lines. `app/adapters/api/purchases.py` exposes receipt routes under `/api/admin/purchases/{purchase_id}/receipts`.

### Extend stock movement provenance with an order receipt origin

- **Decision**: Add a nullable `purchase_order_receipt_item_id` to `inventory_movements`, and adjust the existing origin/type constraints so a purchase receipt points to exactly one invoice-receipt item or order-receipt item.
- **Rationale**: The stock ledger remains the single source of truth for stock changes; an order receipt can be traced without creating an invoice or a synthetic invoice line.
- **Alternatives considered**: Create stock directly in the receipt repository without an inventory movement; rejected because migration 011 and the backend constitution require all stock variation to be traceable. Store the order receipt ID in `reason`; rejected because text is not a referential relationship.
- **Evidence**: `app/adapters/persistence/inventory_movements.py:apply_stock_movement` updates `spare_parts.current_stock` and inserts `inventory_movements` in the caller's transaction. Migration `sql/migrations/011_inventory_movement_traceability.sql` defines origin checks around invoice receipt item and sales order item.

### Do not create a second stock increase from an order-linked invoice

- **Decision**: When `supplier_purchases.purchase_order_id` is set, the invoice is linked as documentation and must not be received through the invoice receipt endpoint. Physical receipt is registered on the purchase order. Invoice rows may map to order lines for billed-quantity visibility.
- **Rationale**: One physical delivery should produce one receipt and one stock movement even if its invoice is created before or after delivery.
- **Alternatives considered**: Let both order and invoice receipt APIs update stock and rely on UI coordination; rejected because retries or independent operators can duplicate stock. Automatically create order receipts from invoice lines; rejected because a supplier invoice alone does not prove physical arrival.
- **Evidence**: Existing purchase creation already validates the optional order FK and supplier match in `app/adapters/persistence/purchases.py`; current invoice receipt flow changes stock for each invoice receipt item.

### Model orders as a small explicit state machine

- **Decision**: New orders start `DRAFT`; ADMIN explicitly issues/cancels. Receipt events move them to `PARTIALLY_RECEIVED` or `RECEIVED`. DRAFT is editable. Cancellation preserves received quantities and cancels only outstanding quantities.
- **Rationale**: It matches the user's confirmed workflow and keeps supplier commitment distinct from physical stock.
- **Alternatives considered**: Mark order as issued on creation; rejected because a draft is needed before the ADMIN explicitly sends it. Allow edits after issue; rejected because changing committed lines invalidates the audit trail; use cancellation and replacement instead.
- **Evidence**: User clarification selected “ADMIN gestiona todo: borrador, emitir, cancelar”; the schema currently has only a free-form `status` field and no order API.

### Preserve snapshots and existing data additively

- **Decision**: Use migration `014_purchase_orders_lifecycle.sql`. Backfill snapshots from available spare-part data or existing custom line names; retain all current identifiers and financial values. Allow a NULL historical description if the linked item was deleted and its custom name is also absent. Do not automatically associate invoice lines with order lines by matching labels. Abort preflight on existing orders or order-linked invoice receipts that need a human-reviewed lifecycle/line mapping instead of silently reinterpreting them.
- **Rationale**: Names can be ambiguous and catalog entries may change. Explicit mapping avoids inventing historical relationships.
- **Alternatives considered**: Rebuild `purchase_orders` from a schema dump; rejected because it is destructive and does not preserve live data. Fuzzy matching historical lines; rejected because an incorrect link contaminates receiving and invoicing totals.
- **Evidence**: The current schema snapshot shows order headers only contain ID, supplier, total, status, estimated arrival and timestamps; order lines contain order ID, nullable spare-part ID, nullable custom name, integer quantity, unit cost and subtotal. No order creator/issue audit fields exist. Read-only inspection of the configured test database reported zero order rows and zero supplier purchases linked to an order at Specify time.

### Safely handle legacy order states and invoice receipts

- **Decision**: Migration preflight fails before applying DDL if legacy order rows require status interpretation or if invoice receipts are attached to order-linked purchases. Keep their rows unchanged and require a reviewed, explicit mapping before retrying the migration. For the current test database, the observed order and linked-purchase counts are zero.
- **Rationale**: The current schema does not record a relation between supplier invoice lines and purchase-order lines, and the old `PENDING` status has no documented state-machine meaning. A safe automatic mapping cannot always be inferred.
- **Alternatives considered**: Assume every invoice receipt line maps by product ID/name or every `PENDING` order is a draft; rejected because duplicated lines, free-text items, split deliveries and undocumented status meaning make the result ambiguous. Ignore previous receipt quantities; rejected because that permits receiving more than ordered.
- **Evidence**: `supplier_purchase_items` and `purchase_order_items` have no direct FK between them in the current snapshot. Previous read-only inspection of the test database found no orders or linked purchases, but migration behavior must still preserve non-empty installations.

## Implementation conventions observed

- FastAPI routers and Pydantic schemas live in `app/adapters/api`; route composition is in `app/infrastructure/chat_app.py`.
- Business services and errors live in `app/application`; deterministic rules live in `app/domain`.
- Persistence uses SQLAlchemy Core `text()` and PostgreSQL transactions in `app/adapters/persistence`.
- ADMIN identity comes from `require_admin` and `SessionCustomer.id`; write payloads do not select actors.
- API validation uses Pydantic `extra="forbid"`; persistence errors are logged by exception type and returned as safe `503` responses.
- Receipts and movement writes already use idempotency and transaction-scoped stock mutation. The order receipt should follow these conventions.
- Schema evolution is kept under `sql/migrations`; the reconstruction SQL is not a migration.

## Unknowns

No unresolved business decisions remain. The implementation phase must confirm exact live-schema state on the configured test database before applying migration 014; this plan does not execute or apply it.
