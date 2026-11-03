# Tasks: Patrones multiagente coherentes y trazables

**Input**: Design documents from `specs/001-patrones-multiagente-coherentes/`

**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/`, `quickstart.md`

**Tests**: Contract, unit, and integration tests are explicitly required by the feature specification and user request. Add tests first for each story and run the targeted test before implementing its behavior.

**Organization**: Tasks are grouped by user story. Complete the shared foundations first, then the stories in order. Keep edits sequential when they touch the same pattern graph or repository file.

## Phase 1: Setup

**Purpose**: Prepare the cross-pattern contract harness without changing runtime behavior.

- [X] T001 Create shared pattern contract fixtures for fake model, repository, customer context, and trace capture in `tests/contract/patterns/conftest.py`.
- [X] T002 [P] Add the scenario matrix and expected side effects to `tests/contract/patterns/scenarios.py` from `contracts/pattern-evaluation.md`.
- [X] T003 [P] Add a schema reference fixture for required expanded tables, columns, and enum labels in `tests/unit/infrastructure/test_expanded_schema_contract.py`.

## Phase 2: Foundational

**Purpose**: Establish shared application capabilities and model configuration before pattern integration.

- [X] T004 Add application ports and typed results for catalog, quotes, customer ticket lookup, warranty, logistics, refunds, and knowledge in `app/application/ports.py`.
- [X] T005 Add stable domain/application error results for ambiguous catalog, insufficient stock, stale quote, ownership, refund eligibility, and unavailable knowledge in `app/application/errors.py` and `app/domain/errors.py`.
- [X] T006 [P] Add shared business capability unit test scaffolding in `tests/unit/application/test_business_capabilities.py`.
- [X] T007 Add a central injectable model-profile factory and validation in `app/settings.py` and `app/adapters/llm/model_factory.py`; retain existing environment variable names and remove pattern-local model defaults.
- [X] T008 Add a shared contract test that verifies all pattern adapters receive the same configured model profile in `tests/contract/patterns/test_model_profile.py`.

**Checkpoint**: Business operations can be called without depending on any pattern's graph state; model configuration is common and injectable.

## Phase 3: User Story 1 - Comparar patrones con las mismas capacidades (Priority: P1)

**Goal**: Keep graph topologies distinct while making shared catalog, quote, access, confirmation, and error behavior equivalent.

**Independent Test**: Run the same catalog/quote scenarios against all three adapters and compare normalized replies and persisted effects.

### Tests for User Story 1

- [X] T009 [P] [US1] Add contract tests for exact/ambiguous catalog matches, stock checks, and database-backed price values in `tests/contract/patterns/test_catalog_contract.py`.
- [X] T010 [P] [US1] Add contract tests for quote calculation, stale price, explicit acceptance, and rejection across all patterns in `tests/contract/patterns/test_quote_contract.py`.
- [X] T011 [P] [US1] Add tests proving model-supplied customer IDs, prices, stock, totals, and status cannot override server data in `tests/contract/patterns/test_untrusted_tool_arguments.py`.

### Implementation for User Story 1

- [X] T012 [US1] Implement the shared catalog and inventory application capability using `ServiceRepository` in `app/application/catalog.py`.
- [X] T013 [US1] Move quote arithmetic, line validation, and total calculation into one Decimal-based application capability in `app/application/quotes.py`; adapt `app/agents/jerarquico/tools/quotes.py` and `app/agents/orquestador/agentes/quotes.py` to delegate or remove them after references are migrated.
- [X] T014 [US1] Add shared LangChain tool wrappers with strict Pydantic inputs and server-injected customer context in `app/adapters/tools/catalog.py` and `app/adapters/tools/quotes.py`.
- [X] T015 [US1] Adapt hierarchical catalog, warehouse, sales, and billing nodes to the shared capabilities while preserving their routing topology in `app/agents/jerarquico/warehouse.py`, `app/agents/jerarquico/sales.py`, and `app/agents/jerarquico/agents/billing.py`.
- [X] T016 [US1] Adapt Orchestrator inventory and sales nodes to the same capability results and quote rules in `app/agents/orquestador/agentes/almacen.py`, `app/agents/orquestador/agentes/ventas.py`, and `app/agents/orquestador/agentes/quotes.py`.
- [X] T017 [US1] Replace decentralized mock catalog/cotization tools with wrappers over the shared capabilities and pass authenticated customer context from graph state in `app/agents/decentralized/tools/`, `app/agents/decentralized/ventas.py`, and `app/agents/decentralized/almacen.py`.
- [X] T018 [US1] Make all pattern adapters advertise equivalent quote/action capability in `app/adapters/patterns/decentralized.py` and `app/application/chat.py` without changing `POST /api/chat` response shape.
- [X] T019 [US1] Run the User Story 1 contract tests and fix parity gaps without merging graph topologies.

## Phase 4: User Story 2 - Respuestas fundamentadas en conocimiento comÃºn (Priority: P1)

**Goal**: Replace the three retrieval implementations with one provenance-preserving source and retrieval interface.

**Independent Test**: Same Spanish query yields the same source passages and abstention behavior through all pattern agents.

### Tests for User Story 2

- [X] T020 [P] [US2] Add ingestion tests for source metadata, deterministic IDs, exact duplicate handling, and stale chunk removal in `tests/unit/rag/test_ingest.py`.
- [X] T021 [P] [US2] Add retrieval tests for Spanish semantic questions, exact SKU/case matching, trust filters, thresholds, and abstention in `tests/unit/rag/test_shared_retriever.py`.
- [X] T022 [P] [US2] Add pattern contract tests for common RAG results and demo-only FAQ facts in `tests/contract/patterns/test_knowledge_contract.py`.

### Implementation for User Story 2

- [X] T023 [US2] Add a single manifest for `data/knowledge/`, hierarchical knowledge-base files, and Orchestrator technical Markdown with explicit area, trust, language, audience, and version metadata in `app/rag/sources.py`.
- [X] T024 [US2] Implement deterministic Markdown loading, section-aware chunking, content digests, deduplication, and stable Chroma IDs in `app/rag/ingest.py`.
- [X] T025 [US2] Configure the shared multilingual FastEmbed model and a versioned Chroma collection without deleting the existing collection in `app/rag/embeddings.py` and `app/rag/ingest.py`.
- [X] T026 [US2] Implement the shared retriever result contract with source metadata, trust filters, relevance abstention, and lexical matching for codes in `app/rag/retriever.py`.
- [X] T027 [US2] Refactor the hierarchical technical and FAQ agents to use the common retriever while retaining their role-specific prompts in `app/agents/jerarquico/retriever.py`, `app/agents/jerarquico/knowledge_retrieval.py`, and `app/agents/jerarquico/agents/faq.py`.
- [X] T028 [US2] Refactor the Orchestrator technical agent to use the common retriever and remove its duplicate lexical retriever after references are migrated in `app/agents/orquestador/knowledge/retriever.py` and `app/agents/orquestador/agentes/tecnico.py`.
- [X] T029 [US2] Refactor decentralized RAG tools and role prompts to call the common retriever and preserve citations/trust labels in `app/rag/tools.py`, `app/agents/decentralized/soporte.py`, `app/agents/decentralized/tecnico.py`, and `app/agents/decentralized/ventas.py`.
- [X] T030 [US2] Run the User Story 2 RAG tests using fake embeddings/vector stores; run an opt-in cached-model smoke test only if the model is already available.

## Phase 5: User Story 3 - Completar flujos de servicio y posventa aplicables (Priority: P1)

**Goal**: Bring all three patterns to the hierarchical flow coverage, including safe refund-request registration and consistent unavailable supplier procurement.

**Independent Test**: Execute the documented flow matrix in each pattern and compare responses, ownership, writes, and status semantics.

### Tests for User Story 3

- [X] T031 [P] [US3] Add shared flow contract tests for support/clarification, direct sales, PC build and modification, quote accept/reject, warranty lookup/claim, payment pending, and logistics preference in `tests/contract/patterns/test_service_flow_contract.py`.
- [X] T032 [P] [US3] Add refund repository/application tests for completed payment, ownership, invalid/over-remaining amount, duplicate unresolved request, and no money movement in `tests/unit/application/test_refund_requests.py` and `tests/integration/test_refund_requests_integration.py`.
- [X] T033 [P] [US3] Add contract tests that supplier requests are consistently unavailable and create no purchase order in `tests/contract/patterns/test_supplier_unavailable.py`.

### Implementation for User Story 3

- [X] T034 [US3] Add a transactional repository operation to validate completed payment ownership, remaining refundable amount, unresolved duplicate, and insert `refunds` with `REQUESTED` in `app/database/repository.py`.
- [X] T035 [US3] Add the shared request-refund use case and domain result in `app/application/refunds.py` and `app/domain/refunds.py`.
- [X] T036 [US3] Route refund intent, collect payment reference/amount/reason, and report pending manual review in the hierarchical graph without changing its supervisor topology in `app/agents/jerarquico/supervisor.py`, `app/agents/jerarquico/graph/state.py`, `app/agents/jerarquico/graph/routing.py`, and `app/agents/jerarquico/graph/builder.py`.
- [X] T037 [US3] Add equivalent refund intent handling and server-context invocation in the Orchestrator graph and state in `app/agents/orquestador/agentes/atencion.py`, `app/agents/orquestador/graph/state.py`, and `app/agents/orquestador/graph/supervisor.py`.
- [X] T038 [US3] Add equivalent refund tool/handoff and handling to the decentralized graph in `app/agents/decentralized/tools/`, `app/agents/decentralized/soporte.py`, `app/agents/decentralized/state.py`, and `app/agents/decentralized/graph.py`.
- [X] T039 [US3] Port missing supported hierarchical capabilities to Orchestrator and decentralized patterns using common use cases: customer ticket lookup, warranty ownership/claim, logistics record validation, and PC-build selection in `app/agents/orquestador/` and `app/agents/decentralized/`.
- [X] T040 [US3] Standardize supplier procurement response and ensure no mock price, supplier, lead time, purchase order, or inventory reservation is produced in all three patterns.
- [X] T041 [US3] Run the User Story 3 contract and repository tests; confirm all invalid or unconfirmed operations produce zero business writes.

## Phase 6: User Story 4 - Alinear y documentar el esquema (Priority: P1)

**Goal**: Keep repository expectations and the expanded schema aligned with auditable evidence and safe future change procedure.

**Independent Test**: Verify required table/column/enum contracts against the expanded schema fixture and review the recorded read-only database comparison.

### Tests for User Story 4

- [X] T042 [P] [US4] Add schema contract coverage for refund request, ticket, quote, payment, warranty, claim, logistics, and inventory fields in `tests/unit/infrastructure/test_expanded_schema_contract.py`.

### Implementation for User Story 4

- [X] T043 [US4] Record the 2026-11-02 read-only schema comparison, confirmed expanded table/column/enum match, and explicit no-DDL-change result in `docs/20-esquema-ampliado-y-trazabilidad.md`.
- [X] T044 [US4] Reconcile repository queries, state enums, and result mappings with the expanded SQL reference; document any remaining mismatch in `app/database/repository.py` and `docs/20-esquema-ampliado-y-trazabilidad.md`.
- [X] T045 [US4] If and only if T044 finds a required schema object missing from the test DB, add an additive versioned migration under `sql/migrations/` and apply it to the test DB with a logged before/after schema summary; never run the destructive context bootstrap.

## Phase 7: User Story 5 - Comparar ejecuciones en LangSmith y limpiar duplicados (Priority: P2)

**Goal**: Make traces comparable and safe, then remove only proven-unused duplicate code.

**Independent Test**: Inspect trace metadata for each pattern and verify redaction; review a reference inventory before and after removing obsolete modules.

### Tests for User Story 5

- [X] T046 [P] [US5] Add cross-pattern trace tests for pattern/scenario/model metadata and hidden inputs/outputs in `tests/contract/patterns/test_trace_contract.py` and `tests/unit/adapters/test_llm_tracing.py`.
- [X] T047 [P] [US5] Add an import/reference contract test for intentionally retained pattern graphs and common RAG entrypoints in `tests/unit/architecture/test_pattern_inventory.py`.

### Implementation for User Story 5

- [X] T048 [US5] Centralize LangSmith trace config and sanitized metadata propagation across pattern adapters in `app/adapters/llm/tracing.py` and `app/adapters/patterns/base.py`.
- [X] T049 [US5] Add stable scenario/model-profile metadata for evaluation runs without customer content in `app/adapters/patterns/base.py` and `tests/contract/patterns/`.
- [X] T050 [US5] Audit duplicate retrievers, quote calculators, configuration helpers, and demo tools against application imports, tests, scripts, and evaluation use; remove only confirmed dead implementations in `app/rag/`, `app/agents/`, and `app/config.py`.
- [X] T051 [US5] Update `features.md`, `docs.md`, and backend README with shared-capability architecture, pattern parity, unsupported purchasing, pending-only refund behavior, RAG provenance, and remaining memory limitation.
- [X] T052 [US5] Run full required validation from `specs/001-patrones-multiagente-coherentes/quickstart.md`; record commands, outcomes, and any skipped external-service tests in `docs/20-esquema-ampliado-y-trazabilidad.md`.

## Dependencies & Execution Order

### Phase Dependencies

- Setup precedes Foundational.
- Foundational tasks block user stories.
- User Stories 1, 2, and 4 share the foundation; complete their contract tests before respective runtime edits.
- User Story 3 depends on shared capability contracts from US1 and the knowledge interface from US2.
- User Story 5 trace cleanup depends on all feature integrations; remove duplicates only after the full reference audit.
- Final validation follows all stories.

### User Story Dependencies

- US1: Shared capabilities, model profile, and quote/catalog parity.
- US2: Can begin after foundation; integration to agents uses US1's shared application boundary.
- US3: Depends on US1's shared operations; its knowledge/diagnosis scenarios depend on US2.
- US4: Schema contract verification can run after setup; final record includes implementation findings.
- US5: Depends on all patterns using shared behavior so traces can be compared on equivalent scenarios.

### Parallel Opportunities

- T001â€“T003 may be prepared in parallel across separate test files.
- US1 catalog and quote contract tests can be authored in parallel, then pattern integration proceeds sequentially by graph.
- US2 ingestion, retrieval, and pattern contract tests can be authored in parallel; the shared retriever must exist before agent refactors.
- US3 flow tests and supplier-unavailable tests can be authored in parallel; the single repository refund operation must be completed before integrating refund paths into graphs.
- US5 trace tests can be authored while US4 documentation is prepared, but no deletion happens before the full reference audit.

## Implementation Strategy

### MVP First

1. Complete setup and foundational ports/model configuration.
2. Deliver US1 common catalog and quote behavior with parity tests.
3. Deliver US2 single retrieval contract and grounded source behavior.
4. Extend supported business flows and refund request registration to all three patterns.
5. Verify schema, traces, cleanup, and the full contract matrix.

### Completion rule

A task is marked `[X]` only after its acceptance behavior is implemented and its targeted tests pass. Keep tasks open if an external service or schema dependency prevents validation; record the blocker and safe partial status rather than claiming parity.


 