# Quickstart: Implementación y validación

## Preconditions

- Use the backend repository root and the existing Python virtual environment.
- Keep the three pattern identifiers registered and use one model profile for comparable runs.
- Tests should inject fake LLM/repository/RAG implementations; no external Groq or LangSmith call is required for contract tests.
- Any database integration check must use the configured test database only, run inside a rollback/isolated transaction where possible, and never print `DATABASE_URL` or row-level personal data.
- `contexto/tablas postgres v2.sql` recreates exported objects in `public` and is destructive. Run it only against a fresh/reinitializable target database. Preserve existing data by applying the relevant versioned migrations instead.

## Contract test cycle

1. Add a scenario to `tests/contract/patterns/` and define its expected semantic outcome and side effects in `contracts/pattern-evaluation.md`.
2. Run the scenario against each pattern adapter with the same fixtures and model profile.
3. Assert customer ownership, policy decisions, persisted results, prohibited writes, and trace metadata. Permit topology-specific node sequence.
4. Fix shared capability behavior before adding pattern-specific exceptions. If a pattern needs an exception, document it as an explicit experimental variable.

## Commands

```powershell
python -m pytest -q tests/contract/patterns
python -m pytest -q tests/unit
python -m pytest -q tests/integration
python -m pytest -q
```

## RAG validation

- Use temporary Chroma storage and deterministic fake embeddings for normal tests.
- Assert Spanish semantic queries retrieve the expected source; exact case IDs/product codes use lexical matching.
- Assert each hit retains source path, section, digest, trust class, model ID, and corpus version.
- Assert duplicate ingestion does not grow duplicate chunks and a changed source replaces stale chunks in the new index version.
- Assert demo-only business facts are excluded from verified customer answers and empty/low-confidence retrieval abstains.
- Run a separate opt-in smoke test only after the multilingual model is cached; never require model downloads for the normal test suite.

## Refund validation

- Eligible completed payment, owned by the authenticated customer → creates `REQUESTED` once; no payment status changes.
- Pending/failed payment, wrong customer, non-positive/over-remaining amount, or unresolved duplicate → no insert.
- The user-facing response states manual review is pending; no money transfer or approval is claimed.

## Database change traceability

- Current schema inspection found the expanded schema present and no required DDL gap.
- If future implementation work needs DDL, add `sql/migrations/NNN_description.sql` plus a concise `docs/` change record before applying to the test DB.
- Record migration name, purpose, affected objects, transaction/rollback approach, application date, and verification result; do not record connection strings or customer rows.

