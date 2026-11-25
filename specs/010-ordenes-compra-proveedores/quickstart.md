# Quickstart: Validar órdenes de compra a proveedores

This is a validation guide for the implementation phase. Do not run the database migration until the implementation and migration review are complete. Use an isolated test database and an ADMIN session.

## Prerequisites

- Backend environment installed using the repository's `requirements.txt`.
- Test PostgreSQL database initialized to the current schema and migrated through 013.
- A test ADMIN account, one active supplier, and at least one active spare part.
- Backend started from the repository root:

```powershell
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

## Validation sequence

1. Authenticate as ADMIN and keep the session cookie for requests.
2. Read the spare part's current stock and movement history.
3. Create a purchase order with two catalog lines using numeric `spare_part_id` values and one optional free-text line. Verify the response is `DRAFT`, includes computed subtotals, and no stock/movement value changed.
4. Edit the draft, retrieve it, and verify line snapshots and totals were recalculated.
5. Issue the order with `POST /api/admin/purchase-orders/{order_id}/issue`. Verify actor/time audit fields and that stock is still unchanged. Verify editing now returns `409`.
6. Record a partial receipt with `POST /api/admin/purchase-orders/{order_id}/receipts` and an `Idempotency-Key`. Verify a catalog line stock delta equals the received quantity, free-text line stock delta is zero, and order status/quantities show the remaining balance.
7. Retry the exact request with the same key. Verify it returns the original receipt without a second movement. Retry with changed quantities under the same key and verify `409`.
8. Register a supplier invoice linked to that order and map invoice lines with `purchase_order_item_id`. Verify order and invoice can be queried independently and invoice creation does not change stock. An invoice without order-line mapping remains visible as unreconciled (`quantity_invoiced: null`).
9. Attempt invoice-based receipt for the order-linked invoice and verify it is rejected, directing physical receipt to the order endpoint. Verify invoice receipts not linked to an order still follow existing behavior.
10. Receive the outstanding quantity, verify `RECEIVED`, then verify a linked invoice cannot be received through the invoice route (409). Test cancellation of a separate unreceived or partially received order with `POST /api/admin/purchase-orders/{order_id}/cancel` and a reason; it must preserve prior stock and received quantity while showing the remainder as cancelled.
11. Test `GET /api/admin/purchase-orders?supplier_id=7&status=ISSUED&date_from=2026-11-01&date_to=2026-11-30&limit=25&offset=0`, then inspect the full receipt and audit history from the detail endpoint.
12. Run the automated checks listed in the feature tasks. Tests must use isolated fixtures, never mutate the `.env` database.

## API contract

See [purchase-orders.openapi.yaml](contracts/purchase-orders.openapi.yaml). The key routes are list/create, detail/update draft, issue, cancel, and order receipts. All require ADMIN session authorization.

## Expected results

- A successful `POST /api/admin/purchase-orders` returns HTTP `201` with `{ "order": { "id": ..., "status": "DRAFT", "total_amount": "...", "currency": "PEN", "items": [...] } }`.
- A successful `GET /api/admin/purchase-orders/{order_id}` returns HTTP `200` with the same order ID, supplier, snapshots, computed totals and audit trail.
- Only confirmed order receipts affect stock.
- Every stock effect has one immutable movement linked to its receipt line.
- A retry does not duplicate receipt, audit event, movement, or stock delta.
- Order receipt totals never exceed ordered quantities, even for concurrent requests.
- Order invoices remain distinct from the physical receipt and from payment status.
- The migration has not been executed by this implementation workflow; review its preflight and target before applying it to a disposable database.
