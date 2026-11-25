# Research: Patrones multiagente coherentes y trazables

**Date**: 2026-11-02

## Decisions

### 1. Reuse business capabilities, not one shared orchestration graph

- **Decision**: Keep the three graph topologies and their pattern-owned states. Move shared rules and operations behind application ports/use cases, with pattern-specific nodes/tools delegating to those capabilities.
- **Rationale**: The user needs academic comparison in LangSmith. Sharing a graph would remove the independent orchestration strategy; duplicating business rules would make the comparison unfair.
- **Alternatives considered**: Three independent agents and tools (continues current drift); one graph used for all patterns (eliminates the comparison); fully shared node instances (creates coupling between incompatible state schemas).

### 2. Use one model profile and one policy source for comparable executions

- **Decision**: Read model name, temperature, and supported provider parameters from the existing centralized settings/factory. Inject the same model profile into each pattern. Record any experiment override as metadata. Share policy/rule text for safety, money, inventory, confirmation, and privacy while allowing role prompts to remain role-specific.
- **Rationale**: The decentralized agents currently hardcode their model while other patterns use environment configuration. This confounds academic comparison.
- **Alternatives considered**: Preserve per-pattern model defaults (not comparable); force identical full prompts (erases role-specific responsibilities).

### 3. Use one canonical knowledge corpus and retrieval interface

- **Decision**: Use the reviewed `app/agents/jerarquico/knowledge_base/` Markdown as the canonical source through one manifest. Return stable source IDs, titles, source class, trust level, language, and document version with retrieved passages. Deduplicate exact content while retaining source references.
- **Rationale**: The hierarchical corpus is the reviewed source selected by the project; excluding unreviewed historical directories avoids competing facts and inconsistent customer answers.
- **Alternatives considered**: Include every historical Markdown directory immediately (can introduce conflicting facts); copy files into another corpus (creates two sources of truth); keep three retrievers (preserves inconsistent recall).

### 4. Keep embeddings optional and use lexical retrieval by default

- **Decision**: Keep `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` and versioned Chroma ingestion behind `RAG_RETRIEVAL_MODE=hybrid`; default all three patterns to the shared lexical retriever.
- **Rationale**: The first deployment target is Render Free, where avoiding an on-demand model download and local vector-store initialization reduces resource and persistence concerns. Lexical results, metadata filters, and abstention remain common across patterns. The hybrid implementation remains available for later evaluation with an appropriate resource plan.
- **Alternatives considered**: Keep the English model (poor language alignment); add an unsupported/custom model (additional registration and packaging work); change to an English reranker (does not solve Spanish recall).
- **Source**: [FastEmbed supported text embedding models](https://qdrant.github.io/fastembed/examples/Supported_Models/) and [FastEmbed project README](https://github.com/qdrant/fastembed/blob/main/README.md).

### 5. Treat demo knowledge as unverified customer-facing data

- **Decision**: Store an explicit trust classification for every source. Technical guidance and PC-build profiles can inform proposals under their own caveats. Business facts labeled as demo (address, hours, payment methods, commercial FAQ) must not be stated as verified operational facts.
- **Rationale**: `faq_servicio.md` explicitly says the business details are demonstration content. Other knowledge files are generic or synthetic; they are not authoritative records of current business operations.
- **Alternatives considered**: Index all Markdown as trusted facts (can disclose fictional information as real); exclude all existing knowledge (removes useful technical guidance).

### 6. Record refunds as pending requests only

- **Decision**: Validate that the payment belongs to the authenticated customer, validate a positive amount not exceeding the eligible payment amount, and create a refund row in `REQUESTED`. Do not change payment status, issue a transfer, or resolve the request automatically. Return the same customer-facing result from each pattern.
- **Rationale**: The database supports refund request and resolution states, but the application has no payment processor or authorized manual-review workflow. User confirmed manual resolution.
- **Alternatives considered**: Automatically mark refund processed (would falsely claim money movement); implement approval/rejection in this task (no operator surface or authorization rules specified); leave it unavailable (does not complete the confirmed request-registration flow).

### 7. Leave supplier purchasing unavailable

- **Decision**: Return a consistent unavailable response until trusted supplier-to-item price and delivery data exist. The current tables can record supplier purchase orders but do not provide an offer/pricing relationship to select a supplier or quote its current price and lead time.
- **Rationale**: `contexto/instruccion.md` records this limitation, and the user explicitly chose to defer supplier purchasing.
- **Alternatives considered**: Infer vendor prices from supplier-level default delivery days (unsafe); fabricate a mapping from product category (not supported by data).

### 8. Database reference is already present in the test database

- **Decision**: Treat the live PostgreSQL database as canonical. On 2026-11-03, `contexto/tablas postgres v2.sql` was regenerated as a schema-only rebuild script from `multiagentedb`, with DROP statements for exported `public` objects. It is for a resettable target; migrations remain the path to evolve an existing database while preserving data.
- **Rationale**: The expanded tables already include refunds, payments, logistics, warranty claims, supplier purchase orders, `quote_details.custom_item_name`, and separate diagnosis fields. The functional gaps are application behavior and consistency.
- **Alternatives considered**: Running the rebuild script against a database with data (destructive and rejected) or using the legacy `sql/creacion_tablas_ingles_sin_inserciones.sql` (it omits current tables and columns).
- **Traceability**: The schema was dumped without row data or DDL execution. The read-only customer-ticket route check returned 200 with quoted tickets. Record any later schema changes in `sql/migrations/`.

### 9. Keep conversation checkpoint persistence out of scope

- **Decision**: Preserve the existing process-memory conversation/checkpointer behavior for this feature and document it as a known limit. Do not introduce Postgres checkpointers or conversation migrations here.
- **Rationale**: Durable conversation persistence was not among the user's confirmed implementation goals. Adding it would expand scope and affect lifecycle/privacy design.
- **Alternatives considered**: Add durable checkpoints now (larger, independent data lifecycle decision); silently claim conversations survive restarts (incorrect).

## Existing implementation evidence

- Three pattern adapters are registered in `app/adapters/patterns/registry.py`.
- Business flow coverage and current known limitations are summarized in `features.md`, `contexto/instruccion.md`, and `contexto/ADR/ADR-003-patrones-multiagente.md`.
- Shared domain/application layers already exist under `app/domain/` and `app/application/`; pattern-specific graphs remain under `app/agents/`.
- Catalog, ticket, quote, payment, warranty, claim, and logistics operations are in `app/database/repository.py`.
- Existing retrieval implementations are `app/rag`, `app/agents/jerarquico/retriever.py`, and `app/agents/orquestador/knowledge/retriever.py`; the latter two are lexical and must be folded into the common interface.
- Existing source files include `data/knowledge/*.md`, `app/agents/jerarquico/knowledge_base/*.md`, and `app/agents/orquestador/knowledge/fallas_comunes.md`.

## Open risks to validate during implementation

- Confirm all hierarchy flows and transition behavior with existing tests before replacing nodes.
- Confirm rate-limit and session ownership remain outside per-pattern tool inputs.
- Confirm prompt redaction covers all three model invocation paths.
- Confirm exact Chroma API behavior and local model caching under pinned `langchain-chroma`/FastEmbed versions before switching collection configuration.
- Do not remove reference/demo modules solely because they are outside API imports; the evaluation harness may rely on them.

