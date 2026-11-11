# Data Model: Catálogo de cuentas y consultas contables

## Existing model to preserve

### `accounting_entries`

Existing fields include the operation date, concept/detail, category, currency, debit/credit totals, status, responsible user, idempotency data, reversal reference/reason, and timestamps. Keep existing immutable-entry and balance invariants. Add a nullable `accounting_plan_id` reference for new entries; it remains NULL for legacy entries. A newly created entry must identify an active plan.

### `accounting_entry_lines`

Existing fields include entry ID, line number, `account_code`, `account_name`, optional description, debit, and credit. Preserve the required code/name snapshots and all amounts. Add nullable `account_id`; it stays NULL for lines created before catalog adoption. New entries require each line to reference an active/postable account from the entry's plan. A reversal copies the account reference and original snapshots.

### Existing audit

Entry creation and reversal events remain in the existing entry audit stream. Configuration and period events are recorded separately so that no existing audit constraints need weakening.

## New entities

### `accounting_plans`

| Field | Meaning / rule |
|---|---|
| `id` | Stable identifier. |
| `code` | Stable internal key; unique. |
| `name` | Display name, e.g. “PCGE Perú”. |
| `jurisdiction` | Country or scope, initially `PE` for the default plan. |
| `edition` | Version label, initially “Modificado 2019”. |
| `source_name`, `source_url` | Publisher and official source for the imported plan. |
| `effective_from`, `effective_to` | Optional validity period; end cannot precede start. |
| `status` | `ACTIVE` or `INACTIVE`. |
| `is_default` | At most one active default plan; initial default is PCGE Perú. |
| `created_by`, timestamps | ADMIN actor and audit timestamps. |

Unique plan identity is `(code, edition)`; active default selection is exclusive. Plans referenced by entries cannot be physically deleted; they may be deactivated while remaining reportable.

### `accounting_accounts`

| Field | Meaning / rule |
|---|---|
| `id` | Stable account identifier. |
| `plan_id` | Required reference to one plan. |
| `code` | Account code, unique within plan edition. |
| `name` | Official/catalog denomination or ADMIN-defined label for custom plans. |
| `parent_account_id` | Optional parent; must belong to the same plan. |
| `account_group` | Classification used for presentation, e.g. asset/liability/equity/income/expense when supplied by the plan. |
| `normal_balance` | `DEBIT` or `CREDIT`; required for postable accounts used in ledger calculations. |
| `is_postable` | Whether new journal lines may use this account. Parent/summary accounts with children are not postable. |
| `status` | `ACTIVE` or `INACTIVE`. |
| `effective_from`, `effective_to` | Validity for new postings; history is retained after expiration. |
| `created_by`, timestamps | ADMIN actor and audit timestamps. |

Validation: unique `(plan_id, code)`; no cycles; parent belongs to same plan; only active, valid, postable accounts accept new lines; accounts used by entries cannot be physically deleted. Catalog edits do not update immutable entry-line snapshots.

### `accounting_periods`

One row per calendar year/month with unique `(year, month)`, state `OPEN` or `CLOSED`, and current transition metadata. A month row is created as OPEN on first use when no row exists; only ADMIN can close/reopen it. Posting and close/reopen operations serialize on the period row so a concurrent close cannot race a new entry. Periods with accounting history cannot be deleted. The operation date maps to the corresponding calendar month.

### `accounting_configuration_events`

Append-only audit for plan creation/update/deactivation, account creation/update/deactivation, default plan changes, and period state transitions. Store entity type/id, action, actor user ID, event timestamp, prior/new state where relevant, and reason (mandatory for reopening). Do not store credentials or request secrets. Access remains ADMIN-only.

## Relationships

```text
AccountingPlan 1 ─── * AccountingAccount
AccountingPlan 1 ─── * AccountingEntry (nullable for legacy only)
AccountingAccount 1 ─── * AccountingEntryLine (nullable for legacy only)
AccountingEntry 1 ─── * AccountingEntryLine
AccountingEntry 1 ─── * AccountingAuditEvent
AccountingPeriod 1 ─── * AccountingConfigurationEvent (state history)
User 1 ─── * AccountingConfigurationEvent (actor)
```

Add indexes for plan/version lookups, parent hierarchy, operation date, account-line references, and monthly period state. There is no direct FK from each entry to a period: the accounting date is authoritative and determines period membership. The monthly row controls whether that date accepts new postings. Reports use the operation date; creation date is not substituted.

## Report projections

### Journal

One row per line, with entry number, operation date, concept, account reference if present, account code/name snapshot, debit, credit, status, and reversal relationship. Sort by operation date, entry number, line number.

### Ledger

One row per movement for a selected catalog account and date range. Include balance before range, each movement, and running balance. For cataloged accounts, calculate signed balance as debit minus credit for `DEBIT` normal balance and credit minus debit for `CREDIT` normal balance. For unlinked historical lines, group by stored code/name, use debit-minus-credit as a signed display value, and mark normal balance as unknown.

### Trial balance

One row per account key in the selected period/range, with opening debit/credit balance, period debit/credit, and ending debit/credit balance. Include unlinked historical rows grouped by stored code/name and marked as legacy. For rows without known nature, calculate the signed balance as debit minus credit and split positive/negative closing balances into debit/credit columns. Totals are calculated over the same filtered entry set and show debit/credit reconciliation.

### Export rows

CSV and XLSX are serializations of the same ordered report projection. CSV uses UTF-8 BOM to open predictably in spreadsheet software; decimal amounts remain exact decimal text/numbers, not float-calculated values. XLSX uses a write-only workbook and explicit number formats. Each file includes report type, date range, generation timestamp and totals. Exceeding the configured row limit returns a clear error instead of dropping records.

## Migration and integrity notes

- Migration is additive and versioned. It must not drop or rewrite existing accounting rows or triggers for balance/immutability.
- Catalog seed stores its source edition and validates imported account codes/relationships and normal-balance assignments before setting PCGE as default. Keep the source dataset as a versioned artifact with a recorded checksum.
- Historical account links remain NULL; only new entries require valid references.
- New writes, lines, audit events, and period checks must be atomic.
- The migration version must be selected only after checking the actual `schema_migrations` ledger and reconciling its `011` inventory record with the repository filename/checksum mismatch.

