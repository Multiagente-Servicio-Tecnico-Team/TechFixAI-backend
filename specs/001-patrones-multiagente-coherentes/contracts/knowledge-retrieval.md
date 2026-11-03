# Shared Knowledge Retrieval Contract

## Source ingestion

- One manifest explicitly registers the existing Markdown sources: `data/knowledge/`, `app/agents/jerarquico/knowledge_base/`, and `app/agents/orquestador/knowledge/`.
- Each source declares stable ID, area, trust class, audience, language, version, and whether it may support customer-facing business facts.
- Chunk IDs are deterministic from source ID, section identity, and content digest. Re-ingestion updates the same logical chunk and removes stale IDs only within the new versioned collection.
- Exact duplicate chunks retain merged source references rather than producing duplicate context.
- No business price or live stock is ingested as authoritative; those come from PostgreSQL at request time.

## Query

`retrieve(query, filters, limit)` returns `RetrievedPassage[]`:

- `content`: bounded passage text.
- `source_id`, `source_path`, `title`, `section`, `content_digest`.
- `area`, `trust_level`, `audience`, `language`, `corpus_version`, `embedding_model`.
- `score` and `match_type` (`semantic`, `lexical_code`, or `hybrid`).

Retrieval uses a shared multilingual semantic index with deterministic lexical matching for product codes, case IDs, and known terms. A relevance threshold/abstention rule prevents passing unrelated matches as evidence. Metadata filters allow excluding demonstration-only business facts from verified operational answers.

## Answer grounding

- Agents receive source metadata with retrieved passages and must preserve uncertainty.
- The final response includes a concise source reference when factual technical guidance is used.
- If no adequate passage exists, the agent says the approved corpus did not provide enough evidence and follows the safe fallback for that workflow.
- Retrieved instructions are untrusted data; prompts must not follow instructions embedded in source text that conflict with system policy.

## Index versioning

- Record corpus manifest version and embedding model ID in collection metadata.
- Build a new collection when model or chunking changes; validate it before switching the active collection.
- Do not delete the previous collection during build. Provide an explicit cleanup task only after validation and a rollback window.

