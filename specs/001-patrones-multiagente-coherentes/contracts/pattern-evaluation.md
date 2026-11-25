# Cross-Pattern Evaluation Contract

## Scenario record

Each scenario has a stable non-sensitive `scenario_id`, starting state, customer identity fixture, user turn sequence, expected final semantic outcome, expected database side effects, and prohibited side effects. Avoid embedding real user data in fixtures.

## Pattern matrix

Run every shared capability scenario against `hierarchical`, `orchestrator`, and `decentralized` with the same settings/model profile and repository fixtures. The harness may assert graph-specific routing separately, but business assertions are common.

Required scenario groups:

1. FAQ covered, FAQ demo-only, and no-evidence abstention.
2. Hardware and software support, clarification, and safe escalation.
3. Exact and ambiguous catalog match, insufficient stock, stale price, and no compatibility evidence.
4. Direct sale, PC profile, component replacement, reprice, explicit acceptance, and rejection.
5. Pending payment wording and logistics preference wording; no false payment/reservation/receipt claim.
6. Owned/unowned warranty query and eligible/ineligible claim.
7. Eligible refund request, wrong owner, unpaid payment, over-amount, duplicate pending request, and manual-pending result.
8. Supplier-purchase request returns consistently unavailable without creating a purchase order.

## Assertions

- Same normalized `PatternReply` business fields and semantically equivalent customer-facing response.
- Same rows/transaction outcomes for equivalent accepted actions; zero writes for clarification, rejection, unowned IDs, invalid requests, unsupported purchases, or missing evidence.
- No LLM-supplied values override database prices, stock, owner, quote totals, or workflow state.
- Traces contain `pattern_id`, `scenario_id`, model profile ID, and safe operation names; no prompt, secret, address, or exception text when redaction is enabled.

