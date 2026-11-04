# Shared Business Capabilities Contract

These capabilities are internal application contracts. Pattern-specific LangGraph nodes/tools may adapt how they call them, but may not duplicate business rules.

## Execution context

Every call receives server-created `CustomerContext`. Tool arguments from a model must not contain authoritative customer identity, prices, stock, payment status, ticket status, or persisted IDs except when the caller selects a user-visible known code that the repository revalidates.

## Operations

| Operation | Input | Output | Required behavior |
|---|---|---|---|
| `search_catalog` | query, family/category, limit | Catalog matches and match status | Only active catalog rows; stable limit; parameterized search; do not infer compatibility. |
| `check_inventory` | exact item code/ID or selected catalog match, quantity | name/code, current stock, current price, availability | Validate positive quantity; re-read live values; no reservation/decrement. |
| `calculate_quote` | quote type, labor type, validated catalog lines | Decimal breakdown and total | One implementation for every pattern; reject invalid/negative quantity/price; money rounded consistently. |
| `save_accepted_quote` | customer context, ticket, confirmed draft | ticket/quote/payment identifiers and pending state | Verify ownership and unchanged price/stock; transaction; only explicit confirmation can write. |
| `get_customer_ticket` | customer context, ticket code | ticket summary or not found | Scope lookup to authenticated customer. |
| `check_warranty` | customer context, warranty code | owned policy status and expiry | Exact code lookup and owner verification. |
| `register_warranty_claim` | customer context, policy, reason | claim code and `IN_REVIEW` | Require policy eligibility; create claim once for the submitted action. |
| `record_logistics_preference` | customer context, ticket, mode, courier/address where required | logistics record/status | Validate required courier data; clearly label as preference/pending receipt. |
| `request_refund` | customer context, payment code, amount, reason | refund request ID/code and `REQUESTED` | Verify ownership; payment must be completed; positive amount within remaining refundable total; reject unresolved duplicate; transaction lock plus insert; no money movement. |
| `retrieve_knowledge` | query, use-case/source filters, limit | Ranked passages with source metadata | Shared source manifest; same corpus/model version; empty/low-confidence result supports abstention. |

## Stable outcomes and errors

- `not_found`, `ambiguous_match`, `insufficient_stock`, `stale_price`, `not_owned`, `not_eligible`, `duplicate_pending`, `invalid_request`, `storage_unavailable`, and `knowledge_unavailable` are mapped to the same user-facing semantics by each pattern.
- Storage errors do not reveal SQL, host names, credentials, or raw exception text.
- Unsupported supplier purchasing returns a clear unavailable result with no mock quote/order.
- A refund request response states that it is pending review and money was not transferred.

