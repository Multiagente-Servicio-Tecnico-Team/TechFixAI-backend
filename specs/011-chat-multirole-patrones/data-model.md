# Data model and runtime contracts

## Authenticated principal

- `role`: `CUSTOMER` or `ADMIN`, derived only from verified session.
- `user_id`: authenticated account identifier; present for both roles.
- `customer_id`: resolved commercial customer identifier for customer operations; never accepted from chat text or client-supplied tool arguments.
- `conversation_id`: opaque identifier scoped to `(role, user_id, pattern)`.

## Conversation

- Owner is `(role, user_id)`; pattern is selected from `hierarchical`, `orchestrator`, `decentralized`.
- Customer and ADMIN state/checkpoints must not be addressable across owners or roles.
- Existing in-memory conversation lifetime remains; a pending ADMIN write is not restored as executable after server restart/session replacement.

## Admin write proposal

- `proposal_id`: opaque UUID/idempotency key.
- `actor_user_id`: authenticated ADMIN.
- `conversation_id` and `pattern_id`.
- `capability`: allowlisted operation name.
- `resource_type` and optional resource identifier.
- `normalized_payload`: validated command fields (never arbitrary SQL or URL).
- `summary`: human-readable effect preview.
- `status`: `PENDING_CONFIRMATION`, `EXECUTED`, `CANCELLED`, `EXPIRED`, or `CONFLICT`.
- `created_at`, `expires_at`, `confirmed_at`, `result_reference`.
- It is held in the existing in-memory conversation state; it has no PostgreSQL table and is lost on process restart or when routed to another instance.
- Confirmation is valid only from the same authenticated actor/conversation, explicit language or structured confirm action, before expiry, and after fresh authorization/domain validation. If state is unavailable, reject confirmation and ask the ADMIN to create a new proposal.

## Shared capability

- `name`, allowed roles, operation kind (`READ` or `WRITE`), input schema, validator, executor, audit actor source, result schema, error mapping.
- CUSTOMER and ADMIN registries are separate allowlists. The LLM sees only tools that are registered for the authenticated role.
- Tools can call application services/repositories; they cannot call peer HTTP APIs or trust model-generated identity.

## Commercial quotation

- Existing `quotes` remains the commercial proposal entity, with `customer_id`, `quote_type`, lines, amount, status, expiry and audit.
- `DIRECT_SALE` and `PC_BUILD`: `ticket_id = NULL`.
- `REPAIR`: non-null service `ticket_id`, with matching commercial customer.
- Acceptance of either sale type uses existing stock reservation and pending payment flow; order is created only after confirmed payment.
- Migration changes `chk_quotes_ticket_kind` and validates existing records before replacing it. Existing PC_BUILD quotes tied to tickets must be reviewed/migrated without losing identifiers, lines or audit; migration must not silently delete them.

## Knowledge source

- `source_id`, canonical relative path, area, trust level, audience, language, revision, content hash, allowed factual domains.
- All patterns use the same source manifest, indexing/chunking/retrieval policy and citations. Live product/price/stock/customer/payment/order data stays in PostgreSQL.

