# Tasks: Chat multirol coherente para los tres patrones

**Input**: Design documents from `specs/011-chat-multirole-patrones/`  
**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/`

## Phase 1: Setup

- [x] T001 Inventory public chat/audio routes, session guards and pattern composition in `app/main.py` and `app/infrastructure/chat_app.py`
- [x] T002 Inventory all client/admin write methods, actor/audit fields and transaction boundaries in `app/adapters/api/` and `app/adapters/persistence/`
- [x] T003 Inventory prompt/model construction and knowledge source usage for hierarchical, orchestrator and decentralized graphs under `app/agents/`

## Phase 2: Foundational

- [x] T004 Define role-aware `Principal`, capability schemas and normalized capability errors in `app/domain/` and `app/application/ports.py`
- [x] T005 Implement shared read/write capability registry with distinct CUSTOMER and ADMIN allowlists in `app/application/capabilities.py`
- [x] T006 Implement role-and-actor-scoped conversation storage and pending proposal lifecycle in `app/application/admin_conversations.py`
- [x] T007 Implement write proposal/confirm/cancel use cases with expiry, same-actor checks, revalidation and idempotency in `app/application/admin_chat.py`
- [x] T008 Add shared role-specific system prompt policy builder for all patterns in `app/application/prompts.py`
- [x] T009 Normalize effective provider/model/temperature profile and runtime injection in `app/adapters/llm/model_factory.py`
- [x] T010 Consolidate ASGI composition so exported app, lifecycle and pattern resources are composed once in `app/main.py` and `app/infrastructure/chat_app.py`

## Phase 3: User Story 1 - Atención coherente al cliente (P1)

**Independent test**: Ejecutar los mismos escenarios CUSTOMER en los tres patrones; verificar propiedad, efectos de ticket/cotización y fuentes.

- [X] T011 [US1] Add customer FAQ, catalog, ticket, quote-acceptance and ownership contracts across `test_customer_parity.py`, `test_catalog_contract.py`, `test_knowledge_contract.py`, `test_quote_contract.py` and `test_service_quote_parity.py`
- [x] T012 [US1] Change supervisor classification so `SALE` and `PC_BUILD` create no service ticket in `app/agents/jerarquico/supervisor.py`
- [x] T013 [US1] Persist standalone PC_BUILD quotes through the sales quotation capability in `app/agents/jerarquico/sales.py`
- [x] T014 [US1] Update hierarchical quote acceptance, reservation, payment and order routing to handle PC_BUILD without ticket in `app/agents/jerarquico/agents/billing.py` and `app/agents/jerarquico/agents/warranty.py`
- [x] T015 [US1] Generalize sale quote persistence/list/get/accept/payment queries to allow `DIRECT_SALE` and standalone `PC_BUILD` in `app/adapters/persistence/sales_quotes.py`
- [x] T016 [US1] Update quote and order repository invariants for standalone PC_BUILD while preserving ticket-only REPAIR in `app/database/repository.py` and `app/database/decentralized_repository.py`
- [x] T017 [US1] Add versioned migration replacing `chk_quotes_ticket_kind` and preserving existing rows/audit in `sql/migrations/015_pc_build_standalone_quotes.sql`
- [x] T018 [US1] Align customer quote API response/type mapping and OpenAPI contract for PC_BUILD in `app/adapters/api/sales_quotes.py` and `app/chat/contract.py`
- [x] T019 [US1] Build one knowledge manifest rooted in reviewed canonical Markdown content and preserve source IDs in `app/rag/sources.py`
- [x] T020 [US1] Route FAQ, technical and sales document retrieval for all graphs through shared ingestion/retriever rules in `app/rag/` and `app/agents/`
- [X] T021 [US1] Add cross-pattern contracts for shared evidence, abstention, live catalog facts, service-quote persistence and ticketless PC_BUILD in `tests/contract/patterns/`

## Phase 4: User Story 2 - Operar el sistema como ADMIN por texto (P1)

**Independent test**: ADMIN can query allowed operational resources; every requested write returns a proposal, and only same-actor explicit confirmation executes it once.

- [x] T022 [US2] Implement ADMIN capability adapters over existing validated application/repository operations for customers, tickets, inventory, supplier purchases, purchase orders, sales quotes and accounting in `app/application/admin_capabilities.py`
- [x] T023 [US2] Implement common ADMIN structured-command service that separates read execution from write proposal/confirmation in `app/application/admin_chat.py`
- [x] T024 [US2] Add authenticated text routes `/api/admin/chat` and `/api/admin/chat/patterns`, response schemas and error mapping in `app/adapters/api/admin_chat.py`
- [x] T025 [US2] Add ADMIN chat dependencies, composition and rate limiting in `app/infrastructure/chat_app.py`
- [x] T026 [US2] Share one ADMIN capability service across the three pattern IDs; retain pattern identity for isolation and trace comparison without routing ADMIN operations through customer graphs in `app/adapters/patterns/`
- [X] T027 [US2] Add ADMIN contract cases for reads, write preview, same-actor confirmation, cancellation, ambiguous confirmation, idempotency and role denial in `tests/contract/patterns/test_admin_chat_parity.py`
- [x] T028 [US2] Verify all admin capability audit fields are attributed to the session ADMIN and that unsupported procurement/refund operations remain unavailable in `app/application/admin_capabilities.py`

## Phase 5: User Story 3 - Usar voz con aislamiento de rol (P1)

**Independent test**: CUSTOMER and ADMIN audio use role-bound conversations; an explicit ADMIN voice confirmation may confirm only that ADMIN's pending proposal.

- [x] T029 [US3] Add ADMIN audio route using the existing transcriber and ADMIN chat use case in `app/adapters/api/admin_chat.py`
- [x] T030 [US3] Scope audio quota/idempotency fingerprint by authenticated role and actor in `app/application/audio_chat.py` and `app/application/audio_requests.py`
- [x] T031 [US3] Apply body limits, no-store headers and safe transcript handling to ADMIN audio in `app/infrastructure/chat_app.py`
- [X] T032 [US3] Add customer/admin audio role-isolation and explicit ADMIN voice-confirmation cases in `test_audio_chat_patterns.py` and `test_admin_chat_parity.py`

## Phase 6: User Story 4 - Comparar los tres patrones con los mismos contratos (P1)

**Independent test**: Runtime model config, capability registry, RAG evidence and normalized effects are equal across all three patterns.

- [x] T033 [US4] Replace hardcoded decentralized `ChatGroq` construction with injected shared model factory in `app/agents/decentralized/`
- [x] T034 [US4] Consolidate shadowed `build_graph` definitions and align runtime flags/repositories in `app/agents/decentralized/graph.py` and `app/adapters/patterns/decentralized.py`
- [x] T035 [US4] Pass the shared model profile and prompt policies to orchestrator agents in `app/agents/orquestador/`
- [X] T036 [US4] Add runtime-effective model profile tests for each graph adapter in `tests/contract/patterns/test_model_profile.py`
- [X] T037 [US4] Add capability parity, role-security and shared-RAG contract coverage in `tests/contract/patterns/`
- [x] T038 [US4] Update `contracts/admin-chat.openapi.yaml`, `contracts/pattern-parity.md` and `contracts/shared-capabilities.md` to the implemented response schemas

## Phase 7: Polish

- [x] T039 Reconcile approved Markdown knowledge into the canonical corpus and document source ownership in `app/agents/jerarquico/knowledge_base/README.md`
- [x] T040 Update feature, runtime and migration documentation in `features.md`, `docs.md`, `memory.md` and `sql/migrations/README.md`
- [x] T041 Review application code for merge artifacts, duplicate builders and stale aliases without deleting referenced compatibility modules in `app/`
- [X] T042 Execute the isolated contract suite and fixture-backed quickstart scenarios; record results and the test-database migration ledger in `quickstart.md`
- [x] T043 [US1] Align Orchestrator service intake, ticket creation, diagnosis persistence, and accepted `REPAIR` quote persistence with the existing-ticket lifecycle in `app/agents/orquestador/graph/supervisor.py`, `app/agents/orquestador/agentes/ventas.py`, and `app/adapters/patterns/orchestrator.py`
- [x] T044 [US4] Document customer/admin text and voice frontend scenarios, expected database effects, role boundaries, and current UI limitations in `docs/30-guia-pruebas-manuales-chat-multirole-frontend.md`
- [x] T045 [US1] Keep the existing service ticket visible in all three pattern adapters while a `REPAIR` quote awaits customer confirmation; add contract coverage for pending and accepted ticket references
- [x] T046 [US1] Persist Descentralizado hardware/software assessments on the authenticated customer's existing service ticket and retain the other specialist's diagnosis in `app/agents/decentralized/graph.py` and `app/database/repository.py`
- [x] T047 [US1] Expose persisted hardware/software diagnosis in `GET /api/customer/tickets` using session-scoped ownership and update the customer contract
- [x] T048 [US1] Add a dedicated FAQ peer agent to the Descentralizado graph, connect validated Soporte handoffs, reuse the shared FAQ retriever/answerer, and return later turns to Soporte; cover the graph flow in focused tests
- [x] T049 [US4] Align the Orquestador's specialized customer-agent roles with the Hierarchical and Descentralizado patterns while preserving one supervisor; split hardware/software, logistics/warranty, sales and billing responsibilities and record the role mapping in the parity contract

## Dependencies

- T001–T003 establish actual wiring and write ownership.
- T004–T010 block all stories.
- US1 (T011–T021) depends on the foundational layer and schema decision; its migration is required before applying standalone PC_BUILD to a database.
- US2 (T022–T028) depends on T004–T008 and T010; capability adapters must reuse validated operations.
- US3 (T029–T032) depends on US2's ADMIN identity/conversation service and the existing audio use case.
- US4 (T033–T038) depends on shared contracts from T004–T009; it can be integrated alongside US1/US2 only after the shared contract is stable.
- Polish (T039–T042) depends on all accepted stories.

## Suggested MVP

Deliver US1 + US4 first: align customer behavior/RAG/model and PC_BUILD quote semantics. Then add ADMIN text (US2), followed by role-scoped audio (US3). The combined feature is complete only after all four stories and the migration are validated.



Implementation note: all three customer patterns persist accepted REPAIR quotes against service tickets and leave payment pending; they do not reserve inventory for service quotes. Direct-sale and PC_BUILD quotes persist without service tickets; explicit acceptance reserves stock and leaves payment pending. ADMIN write confirmation, cancellation, role isolation, audio role scoping, model profiles and shared-RAG contracts have automated coverage. Migrations 015 and 016 are recorded in the local test database; other environments must apply and verify them separately.
