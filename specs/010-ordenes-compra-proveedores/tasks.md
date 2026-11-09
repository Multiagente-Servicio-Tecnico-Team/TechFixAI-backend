# Tasks: Gestión de órdenes de compra a proveedores

**Input**: Design documents from `specs/010-ordenes-compra-proveedores/`  
**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/purchase-orders.openapi.yaml`, and `quickstart.md`

**Organization**: Tasks are ordered by the five user stories. Story tasks have labels `[US1]`–`[US5]`; setup, foundation, and polish tasks do not.

## Phase 1: Setup

**Purpose**: Prepare documentation and isolated validation scaffolding for the feature.

- [X] T001 [P] Add the migration 014 entry, ordering, prerequisites, and safe rollback notes to `sql/migrations/README.md`.
- [X] T002 [P] Add shared isolated PostgreSQL fixtures for purchase-order API integration tests in `tests/integration/conftest.py`; never load connection settings from the developer `.env` in test fixtures.
- [X] T003 [P] Add a schema-contract test scaffold for migration 014 in `tests/unit/infrastructure/test_purchase_orders_schema_contract.py`, including required tables, foreign keys, idempotency uniqueness, and inventory-movement origin checks.

## Phase 2: Foundational

**Purpose**: Complete prerequisites that every purchase-order story depends on.

- [X] T004 Create `sql/migrations/014_purchase_orders_lifecycle.sql` as a transaction with a fail-fast preflight for legacy order rows and linked invoice receipts; add order audit and order-receipt tables, snapshots, actor fields, lifecycle checks, filters, optional invoice-line mapping, and the new inventory movement origin without dropping or rewriting existing purchase history.
- [X] T005 [P] Complete migration schema-contract assertions in `tests/unit/infrastructure/test_purchase_orders_schema_contract.py` for every table, constraint, index, and fail-fast legacy-data condition introduced by migration 014.
- [X] T006 [P] Add unit cases for the order-receipt movement origin, exactly-one purchase origin, and source projection in `tests/unit/adapters/test_inventory_movements.py`.
- [X] T007 Extend `app/adapters/persistence/inventory_movements.py` so `apply_stock_movement` accepts an order-receipt-item origin, enforces exactly one purchase-receipt origin, and returns the corresponding source in movement projections; implement the schema constraint changes only in migration 014.
- [X] T008 Add `PurchaseOrderError`, not-found, conflict, validation, and storage-unavailable errors in `app/application/errors.py`, mapping them to the existing safe error-response conventions.
- [X] T009 Add `/api/admin/purchase-orders` to the `Cache-Control: no-store` paths in `app/infrastructure/chat_app.py`, preserving the existing purchases path mapping.

## Phase 3: User Story 1 — Crear y consultar órdenes (Priority: P1)

**Goal**: ADMIN can create a draft order with catalog or free-text lines and retrieve its persisted details.

**Independent test**: Create a draft with two lines, retrieve it, and verify supplier, snapshots, computed totals and `DRAFT`; stock and movement counts remain unchanged.

- [X] T010 [P] [US1] Add unit cases for draft validation, required supplier and lines, positive integer quantities, valid exact-decimal costs, and server-calculated totals in `tests/unit/domain/test_purchase_orders.py`.
- [X] T011 [P] [US1] Add isolated API cases for ADMIN create/detail/draft-edit, unauthorized access, inactive supplier, invalid lines and no stock change in `tests/integration/test_purchase_orders_api.py`.
- [X] T012 [US1] Define purchase-order and line draft/value objects, decimal calculations, required descriptions for new lines, and validation errors in `app/domain/purchase_orders.py`.
- [X] T013 [US1] Implement create/edit-draft transactions, active-supplier validation, spare-part snapshots, computed totals, creator audit and order detail projection in `app/adapters/persistence/purchase_orders.py`.
- [X] T014 [US1] Implement create, detail and draft-update application methods with domain validation and repository error translation in `app/application/purchase_orders.py`.
- [X] T015 [US1] Define Pydantic write/patch/response models and implement `POST /api/admin/purchase-orders`, `GET /api/admin/purchase-orders/{order_id}`, and draft-only `PATCH /api/admin/purchase-orders/{order_id}` in `app/adapters/api/purchase_orders.py`.
- [X] T016 [US1] Register the purchase-order router and repository factory in `app/infrastructure/chat_app.py`, using the existing `require_admin` dependency.
- [X] T017 [US1] Verify draft creation, editing and detail against the acceptance scenarios in `specs/010-ordenes-compra-proveedores/quickstart.md` and update expected response examples there.

## Phase 4: User Story 2 — Emitir y cancelar órdenes (Priority: P1)

**Goal**: ADMIN explicitly issues a draft and can cancel an order while retaining received history and stock.

**Independent test**: Issue a valid order, verify actor/time, reject edits after issue, cancel an unreceived or partially received order, and reject cancellation of a fully received order.

- [X] T018 [P] [US2] Add unit tests for allowed/forbidden order transitions and cancellation preserving received quantities in `tests/unit/domain/test_purchase_orders.py`.
- [X] T019 [P] [US2] Add API tests for issue, cancel reason validation, duplicate transition, immutable issued lines, ADMIN authorization, and audit fields in `tests/integration/test_purchase_orders_api.py`.
- [X] T020 [US2] Implement allowed state transitions and validation for issue/cancel commands in `app/domain/purchase_orders.py`.
- [X] T021 [US2] Implement row-locked issue and cancel transactions with actor/time fields and append-only audit events in `app/adapters/persistence/purchase_orders.py`.
- [X] T022 [US2] Add issue/cancel application methods and safe handling of invalid transitions in `app/application/purchase_orders.py`.
- [X] T023 [US2] Implement `POST /api/admin/purchase-orders/{order_id}/issue` and `POST /api/admin/purchase-orders/{order_id}/cancel` with required reason in `app/adapters/api/purchase_orders.py`.
- [X] T024 [US2] Verify order issuance and cancellation behavior in `specs/010-ordenes-compra-proveedores/quickstart.md`.

## Phase 5: User Story 3 — Registrar recepción física (Priority: P1)

**Goal**: ADMIN records partial or complete delivery against order lines; only received catalog quantities affect stock once.

**Independent test**: Issue a 10-unit order, receive 4, verify stock +4 and six pending; replay same key for no second movement; receive remaining six and verify `RECEIVED`.

- [X] T025 [P] [US3] Add unit tests for positive integer receipt quantities, duplicate line IDs, receipt hash normalization, and over-receipt rejection in `tests/unit/domain/test_purchase_orders.py`.
- [X] T026 [P] [US3] Add API tests for partial receipt, free-text line with no stock delta, draft-order rejection, idempotent replay, changed-payload conflict and stock rollback on failure in `tests/integration/test_purchase_order_receipts.py`.
- [X] T027 [US3] Implement receipt draft validation, quantity aggregation, state recalculation, and canonical idempotency request hashing in `app/domain/purchase_orders.py`.
- [X] T028 [US3] Implement transaction-scoped order/line locks, order-specific receipt rows, actor audit, and idempotent replay in `app/adapters/persistence/purchase_orders.py`.
- [X] T029 [US3] Apply one inventory movement per catalog receipt line through `app/adapters/persistence/inventory_movements.py`; do not create a movement for free-text lines and do not exceed stock limits.
- [X] T030 [US3] Add receive/list-receipts application methods and translate idempotency, state and persistence errors in `app/application/purchase_orders.py`.
- [X] T031 [US3] Implement `POST /api/admin/purchase-orders/{order_id}/receipts` with required `Idempotency-Key` and `GET /api/admin/purchase-orders/{order_id}/receipts` in `app/adapters/api/purchase_orders.py`.
- [X] T032 [US3] Verify stock deltas, replay, concurrency and no partial transaction effects using `specs/010-ordenes-compra-proveedores/quickstart.md`.

## Phase 6: User Story 4 — Vincular factura a la orden (Priority: P2)

**Goal**: Supplier invoices remain separate, can link to an order and its lines, and never produce a duplicate stock receipt.

**Independent test**: Receive against an order, create an invoice linked to that order, retrieve both records, verify mapped invoiced quantities and no stock change; reject invoice-based receipt for that linked purchase.

- [X] T033 [P] [US4] Add tests for optional invoice-line mapping, order/supplier mismatch, mapped line ownership and rejection of invoice receipt for order-linked purchases in `tests/integration/test_purchase_order_receipts.py`.
- [X] T034 [US4] Extend purchase line validation to accept nullable `purchase_order_item_id` only when the header has a matching `purchase_order_id` in `app/domain/purchases.py`.
- [X] T035 [US4] Persist invoice-to-order-line mapping and verify each mapped line belongs to the header order and supplier in `app/adapters/persistence/purchases.py`.
- [X] T036 [US4] Reject `receive_purchase` when the supplier purchase is linked to an order, returning a conflict that directs receipt to the order endpoint in `app/adapters/persistence/purchases.py` and `app/adapters/api/purchases.py`.
- [X] T037 [US4] Return invoiced quantity as zero when no invoice is linked, a decimal string when all invoice lines are mapped, and null when linked invoice lines remain unmapped in `app/adapters/persistence/purchase_orders.py`.
- [X] T038 [US4] Update `PurchaseLineWrite` and the order-linked receipt conflict description in `specs/006-registro-compras-proveedores/contracts/purchases.openapi.yaml`.
- [X] T039 [US4] Verify invoice linkage, supplier consistency, and no duplicate movement in `specs/010-ordenes-compra-proveedores/quickstart.md`.

## Phase 7: User Story 5 — Buscar órdenes e inspeccionar historial (Priority: P2)

**Goal**: ADMIN can filter/paginate orders and inspect quantities, linked invoices, receipts and audit history.

**Independent test**: List by supplier, status and date range; open a result and verify ordered, received, pending, invoiced and cancelled quantities plus actors/events.

- [X] T040 [P] [US5] Add integration tests for filters, pagination, empty results, detail aggregates and audit history in `tests/integration/test_purchase_orders_api.py`.
- [X] T041 [US5] Implement bounded paginated list queries and supplier/status/date filters in `app/adapters/persistence/purchase_orders.py`.
- [X] T042 [US5] Extend detail projection with per-line received/pending/invoiced/cancelled quantities, linked purchase documents, receipt history and audit events in `app/adapters/persistence/purchase_orders.py`.
- [X] T043 [US5] Implement list filters and pagination validation in `app/application/purchase_orders.py`.
- [X] T044 [US5] Implement `GET /api/admin/purchase-orders` filters and response metadata in `app/adapters/api/purchase_orders.py`.
- [X] T045 [US5] Verify filtered list and complete order history in `specs/010-ordenes-compra-proveedores/quickstart.md`.

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Align contracts and operational docs, and run feature validations.

- [X] T046 [P] Update migration operations, preflight query, safe retry guidance, and rollback limitations in `sql/migrations/README.md`.
- [X] T047 [P] Update API endpoint inventory and order/receipt behavior in `docs/24-api-inventario.md`.
- [X] T048 Verify all new OpenAPI routes, schemas, error responses and the purchase-line mapping against implemented handlers in `specs/010-ordenes-compra-proveedores/contracts/purchase-orders.openapi.yaml` and `specs/006-registro-compras-proveedores/contracts/purchases.openapi.yaml`.
- [X] T049 Run unit, schema-contract and integration test suites for the purchase-order feature using isolated test fixtures; do not run them against the developer `.env` database.
- [X] T050 Check formatting, API docs and quickstart commands, then review the final diff for accidental changes to `.env`, production schema dumps, or unrelated feature files.

## Dependencies

```text
Setup (T001-T003)
  -> Foundational (T004-T009)
    -> US1 (T010-T017)
      -> US2 (T018-T024)
        -> US3 (T025-T032)
          -> US4 (T033-T039)
            -> US5 (T040-T045)
              -> Polish (T046-T050)
```

- US2 depends on US1 because it transitions persisted orders.
- US3 depends on US1 and US2 because only issued orders accept physical receipts.
- US4 depends on US1 and US3 so invoice association can be validated against the order lifecycle and tested after receipt.
- US5 depends on prior stories because complete detail aggregates receipts, invoice lines and audit events.

## Parallel Opportunities

- Setup documentation (T001), isolated test fixture setup (T002), and schema test scaffold (T003) touch separate files and can be prepared in parallel.
- During US1, domain tests (T010), API tests (T011), domain rules (T012), and schema/route implementation can be split by file after migration/foundational tasks are complete.
- US2 unit tests (T018) and API tests (T019) are independent; implementation in domain (T020) and persistence (T021) can proceed separately once their interfaces are agreed.
- US3 domain tests (T025), API tests (T026), and the shared movement-origin change (T006) are separable after migration 014 is agreed.
- US4 contract updates (T038) can be drafted in parallel with validation work, while persistence and API changes remain coordinated.
- Polish docs (T046, T047) can be updated in parallel once endpoint names are stable.

## Parallel Example: User Story 1

```text
Task A: T010 — Domain validation cases in tests/unit/domain/test_purchase_orders.py
Task B: T011 — API acceptance cases in tests/integration/test_purchase_orders_api.py
Task C: T012 — Pure order draft calculations in app/domain/purchase_orders.py
Task D: T013 — Transactional persistence in app/adapters/persistence/purchase_orders.py
```

## Implementation Strategy

### MVP First

1. Complete Setup and Foundational tasks, especially migration 014 review and shared movement provenance.
2. Complete User Story 1 to create and inspect a draft order without stock effects.
3. Complete User Story 2 to issue/cancel the order.
4. Complete User Story 3 to record physical receipt and stock movement exactly once. This is the first operationally useful MVP.

### Incremental Delivery

1. Deliver draft order create/detail.
2. Add issue/cancel lifecycle.
3. Add direct order receipt with concurrency and idempotency protection.
4. Link invoice headers/lines and disable duplicate invoice-based receipt for linked purchases.
5. Add filtering and full history views.
6. Complete docs and run isolated checks; only then apply the reviewed migration to the authorized test database.

## Notes

- Every task follows `- [ ] T### [P?] [US#?] Description with file path`.
- Tasks T010-T050 include automated test work because the specification includes explicit independent test scenarios, measurable behavior, and the backend constitution requires contract tests.
- Migration 014 must not run until its fail-fast legacy-data preflight and the diff have been reviewed.
- No task changes frontend files or applies a database migration automatically.
