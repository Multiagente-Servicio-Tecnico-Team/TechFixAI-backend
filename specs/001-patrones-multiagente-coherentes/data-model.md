# Data Model: Patrones multiagente coherentes y trazables

## Scope

This feature reuses the expanded PostgreSQL business schema. It does not persist new pattern-run or conversation records and does not require a DDL change based on the read-only schema comparison performed 2026-11-02.

## Shared runtime context

| Field | Source | Rule |
|---|---|---|
| `customer_id` | Verified signed session, passed by application use case | Never accepted from LLM tool arguments or untrusted request content. |
| `conversation_id` | Existing chat conversation registry | Pattern is fixed for the conversation. In-memory lifetime remains unchanged. |
| `pattern_id` | Pattern adapter registry | One of the three registered identifiers; included in trace metadata. |
| `scenario_id` | Evaluation harness/test configuration | Non-sensitive stable identifier; never include raw customer prompt in tags/metadata. |
| `model_profile` | Central application settings/model factory | Identical default configuration for comparable runs; explicit overrides are recorded. |

## Existing business entities

| Entity | PostgreSQL table(s) | Relevant rules |
|---|---|---|
| User/customer | `users` | Customer identity is resolved from the signed session. |
| Catalog item | `spare_parts` | Active item; current price and stock are read from PostgreSQL. Catalog text is not evidence of live availability. |
| Ticket | `tickets` | Belongs to one customer; request type and status use schema enums; hardware/software diagnoses remain separate. |
| Quote | `quotes`, `quote_details` | Quote belongs to a ticket; one ticket may have multiple quote versions in the expanded schema. Total must equal labor plus line subtotals. |
| Payment | `payments` | Belongs to customer/ticket and may reference a quote. `PENDING` is not a completed payment. |
| Refund request | `refunds` | Belongs to payment and ticket; initial status is `REQUESTED`; a manual actor resolves it later. |
| Logistics record | `logistics_records` | Belongs to ticket; selected mode is a preference/record until receipt/delivery status changes. |
| Warranty | `warranties` | Belongs to customer and may link ticket/quote; code must be checked against authenticated customer. |
| Warranty claim | `warranty_claims` | Links warranty and optional ticket; initial claim status is `IN_REVIEW`. |
| Supplier/purchase order | `suppliers`, `purchase_orders`, `purchase_order_items` | Records purchase orders but does not provide a trusted supplier-offer relationship for quoting product price/lead time; purchasing remains unavailable. |

## Shared application value objects

These are application/domain contracts, not new database tables.

### `CustomerContext`

- `customer_id: int`, taken from verified authentication.
- `conversation_id: str`, current conversation reference.
- `pattern_id: str`, selected pattern.

### `CatalogMatch`

- `item_id`, `code`, `name`, `category`, `description`.
- `unit_price: Decimal`, `current_stock: int`, `active: bool`.
- `match_status`: `exact`, `family_options`, `ambiguous`, or `not_found`.
- Match result must not imply compatibility.

### `QuoteDraft`

- `ticket_id`, `quote_type`, `labor_task_type`.
- `labor_cost: Decimal`, line items with catalog item ID, quantity, unit price and subtotal.
- `parts_cost: Decimal`, `total_amount: Decimal`, `currency`.
- `quote_status`: proposed, accepted, rejected, or stale/changed in runtime mapping.
- Only a server-validated accepted draft is persisted; prices and stock are re-read before acceptance.

### `RefundRequestDraft`

- `payment_id`, `ticket_id`, authenticated `customer_id`.
- `amount: Decimal`, `reason: str`.
- Persisted status is `REQUESTED` only.
- Eligibility: payment belongs to customer and is `COMPLETED`; amount is positive and does not exceed remaining refundable amount; no unresolved request exists for the same payment. A payment-row transaction lock protects the eligibility check and insert.
- Resolution is manual; no payment-status transition or money movement occurs in this feature.

### `KnowledgeSource` and `RetrievedPassage`

- Source identity: stable source key, relative path, title/section, content digest, source version.
- Source classification: `technical_guidance`, `business_demo`, `catalog_profile`, or another explicitly registered class.
- Trust: `approved_operational`, `technical_reference`, or `demonstration_only`.
- Retrieval output: passage text, source reference, source class/trust, retrieval score, corpus/model version.
- `demonstration_only` business facts cannot be stated as verified operational facts.

## Relationships and lifecycles

```text
Customer 1 ── * Ticket 1 ── * Quote 1 ── * QuoteDetail * ── 0..1 CatalogItem
                    │             ├── * Payment 1 ── * RefundRequest
                    │             └── * Warranty
                    ├── * LogisticsRecord
                    └── * WarrantyClaim * ── 1 Warranty
```

- Quote: draft → customer confirmation → persisted/accepted; rejection does not persist an accepted quote.
- Payment: created as `PENDING`; payment completion requires a separate verified payment process not implemented by chat.
- Refund: requested → manually resolved (`APPROVED`, `REJECTED`, `PROCESSED`, as authorized outside this feature).
- Logistics: preference/record → later receipt/dispatch/delivery state changes; recording preference does not mean fulfillment.
- Warranty claim: registered in review → manual resolution.

