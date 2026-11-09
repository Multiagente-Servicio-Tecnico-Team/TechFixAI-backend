# Implementation Plan: Patrones multiagente coherentes y trazables

**Branch**: `feature/spec-kit` | **Date**: 2026-11-02 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/001-patrones-multiagente-coherentes/spec.md`

## Summary

Keep the three LangGraph topologies for academic comparison while moving business rules, catalog operations, quote/refund policies, and knowledge retrieval behind shared application capabilities. Bring each pattern to the hierarchical pattern's supported business-flow coverage, preserve topology-specific routing, standardize LangSmith metadata and contract evaluation, and remove only verified dead implementations. Use the expanded PostgreSQL schema as canonical. The configured test database already matches its tables, columns, and enums, so no DDL change is currently required; document that inspection and add a versioned migration only if implementation uncovers a real schema gap. Supplier purchasing remains unavailable, and refund requests are recorded as pending for manual review only.

## Technical Context

**Language/Version**: Python; local interpreter observed as 3.14.4. Deployment runtime compatibility must remain aligned with existing project configuration.

**Primary Dependencies**: FastAPI 0.142.2, LangGraph 1.2.2, LangChain Core 1.6.6, LangChain Groq 1.1.3, SQLAlchemy 2.1.1, Pydantic 2.13.5, Chroma 1.1.0, FastEmbed 0.8.1, pytest 8.4.2.

**Storage**: PostgreSQL through SQLAlchemy and pg8000; the current RAG runtime searches Markdown lexically, with the Chroma collection retained for optional hybrid retrieval; current conversation registries/checkpointers remain in process memory.

**Testing**: Existing pytest unit/integration/e2e suites plus new pattern contract tests, using fake LLMs, repository ports, deterministic knowledge fixtures, and isolated test database transactions where needed.

**Target Platform**: Existing backend API deployment and local developer environments. No frontend contract change is planned.

**Project Type**: Python backend web service with three LangGraph orchestration adapters.

**Performance Goals**: Keep the default retrieval path light enough for Render Free by avoiding model downloads and vector-store initialization; if hybrid retrieval is enabled later, load the shared embedding model/vector collection once per process. Establish numeric latency baselines during implementation rather than inventing an SLA.

**Constraints**: Preserve the `/api/chat` contract and pattern selection. Keep topology and graph-state differences for academic comparison. Business writes must validate customer ownership and use existing transaction boundaries. No supplier price/lead-time claims without supplier-item data. No payment gateway or automatic refund settlement. No conversation-persistence redesign in this scope.

**Scale/Scope**: Three patterns; common flows include FAQ, hardware/software support, catalog/direct sale, PC-build profiles and modifications, inventory selection, quote acceptance/rejection, payment pending, refund request registration, warranty lookup/claim, and logistics preference. Supplier procurement remains an explicit unavailable path.

## Constitution Check

| Gate | Status | Evidence |
|---|---|---|
| Preserve independent orchestration topologies while sharing business rules | PASS | Separate graph builders remain under `app/agents/{jerarquico,orquestador,decentralized}`; common capabilities are application ports/use cases. |
| Money, inventory, authorization, confirmation, and state transitions are server validated | PASS | Reuse `Decimal`, PostgreSQL repository transactions, customer identity from signed session, explicit quote acceptance. |
| Grounded answers, privacy, and tracing | PASS | Common retriever returns source metadata; demo sources are labeled; LangSmith input/output redaction remains enabled. |
| Safe and traceable schema changes | PASS | Read-only inspection confirms current test DB matches expanded schema. Do not run the destructive context bootstrap; create a versioned additive SQL migration only if a real gap is found. |
| Contract tests across all patterns | PASS | Run the same capability scenarios through all three adapters; allow internal routing differences. |
| Remove code only after reference audit | PASS | Check application imports, tests, scripts, and evaluation harness before deleting duplicate retrievers/tools. |

No constitution violations identified. Re-check after design: keep in-memory checkpoint limitation explicit and do not accidentally turn this feature into a persistence rewrite.

## Phase 0: Research Decisions

See [research.md](research.md). The important choices are: share application capabilities and tool schemas, not orchestration graphs; use the reviewed hierarchical Markdown corpus and one lexical retrieval implementation by default; keep versioned Chroma collections available for a future hybrid mode; use an explicit pending refund request; and leave supplier purchasing unavailable until a real supplier-item quote source exists.

## Phase 1: Design & Contracts

See [data-model.md](data-model.md), [contracts/](contracts/), and [quickstart.md](quickstart.md).

- Define common `Catalog`, `Quote`, `Knowledge`, `Ticket`, `Warranty`, `Logistics`, and `Refund` use-case contracts.
- Keep graph-specific state and routing inside each pattern. Each graph delegates to the same application operations and adapters map results into its state.
- Define common document/source metadata and retrieval result contract.
- Define common scenario contract matrix for all three patterns, including expected business side effects and permitted routing variance.
- Define trace metadata keys for pattern, scenario, run/model and sanitized result, avoiding raw conversation text and secrets.

## Project Structure

### Documentation (this feature)

```text
specs/001-patrones-multiagente-coherentes/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── business-capabilities.md
│   ├── knowledge-retrieval.md
│   └── pattern-evaluation.md
├── checklists/
│   └── requirements.md
└── tasks.md
```

### Source Code (repository root)

```text
app/
├── domain/                 # Shared business invariants and entities
├── application/            # Use cases and ports shared by patterns
├── adapters/
│   ├── api/                 # Existing chat contract, unchanged
│   ├── patterns/            # Pattern registry and common trace config
│   └── tools/               # Shared LangChain tool wrappers, if needed
├── rag/                     # One source manifest, ingestion, retriever, provenance
└── agents/
    ├── jerarquico/          # Hierarchical graph topology and state
    ├── orquestador/         # Supervisor graph topology and state
    └── decentralized/       # Handoff graph topology and state

sql/
└── migrations/              # Additive, versioned SQL only if schema changes

docs/                         # Schema and implementation change log
tests/
├── contract/patterns/        # Same scenario contracts for all patterns
├── unit/
├── integration/
└── e2e/
```

**Structure Decision**: Extend the existing layered backend. Pattern folders keep their own graph nodes/states and academic topology. Shared tools wrap application capabilities; agents may adapt invocation to their pattern but cannot fork business rules. Existing knowledge files remain authored in their current locations and are registered through one shared source manifest until a separate content migration is justified.

## Data and Schema Strategy

- Canonical schema rebuild script: `contexto/tablas postgres v2.sql`, generated from `multiagentedb` with schema-only clean output. It drops and recreates exported `public` objects and is only for a resettable target; existing databases use versioned migrations.
- The configured test database was inspected read-only on 2026-11-02. Its public tables, relevant columns and enum labels match the expanded reference, including `refunds`, `payments`, `purchase_orders`, `purchase_order_items`, `quote_details.custom_item_name`, and separate diagnosis fields.
- No database writes or DDL were performed during inspection. The feature currently needs no schema change to register pending refund requests.
- If implementation finds a required missing column/constraint, add a numbered additive SQL migration plus a change record before applying it to the test DB. Never recreate populated tables as a migration.

## Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Patterns diverge while their graph state remains different | Share use cases and contracts; add cross-pattern scenario matrix and assert business effects, not node order. |
| Rebuilding Chroma mixes embeddings or loses provenance | Version collection by embedding/corpus version; use stable IDs and keep the old collection until the new one is validated. |
| Demo shop facts are repeated across sources | Put trust/locale/domain metadata in the source manifest; exclude demo business facts from verified customer answers. |
| Existing flows have legacy semantics (quote stages, warranties, PC selection) | Port behavior from hierarchical flow with characterization tests before replacing internals. |
| LangSmith traces leak content from one path | Centralize trace context/metadata and test redaction; do not add raw content to tags or metadata. |
| Large scope hides incomplete edge flows | Implement incrementally by story and retain parity checklist for each pattern. |

## Complexity Tracking

No constitution violations require justification. Three graph topologies are retained because academic comparison is an explicit project requirement; shared business capabilities prevent that comparison from duplicating rules.
