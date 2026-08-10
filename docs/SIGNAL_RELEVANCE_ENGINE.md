# Signal Relevance Engine

## Principle

**The site should look like a publication. The data layer should behave like a growing brain.** Readers should see calm editorial surfaces, not a database console; the backend should accumulate normalized relationships, provenance, and retrieval signals.

## Current stage

K-Signal already has:

- a four-record master `outputs/search/cards_index.json` and an identical public-safe host snapshot;
- Pagefind browser search and local index shards;
- issue/card IDs, routes, publication status/dates, lanes, topic tags, entity tags, source platform/type, bilingual original/translation text, `internet_read`, `public_summary`, keywords, and normalization fields;
- topic, entity, and lane indexes in the host package;
- stable classes/data attributes and IME/CJK-aware search architecture.

The structured index captures editorial meaning; Pagefind serves public full-text retrieval. They should remain complementary.

## Near term

1. Implement deterministic related-card scoring from the approved point table.
2. Normalize topic/entity aliases into stable IDs while preserving original display labels.
3. Add editorial include/exclude/pin overrides with reasons.
4. Convert verified correction/comment relationships into non-public linkage signals; never use raw volume as truth.
5. Normalize source-platform and source-type IDs.
6. Emit per-candidate score explanations for tests and editorial review.
7. Add tests for self-exclusion, publication eligibility, ties, alias matching, and exactly-two output.

## Mid term

- Generate multilingual embeddings from `public_summary`, `internet_read`, receipts, and normalized entities.
- Blend semantic similarity with deterministic features; keep explainable factors visible internally.
- Build topic, entity, lane, and cluster pages.
- Detect emerging topics through time-windowed cluster growth, source diversity, and correction-aware confidence.
- Build a source graph linking platforms, boards/categories, entities, issues, and cited public URLs.
- Measure discovery quality with editorial judgments and click-through, not engagement alone.

## Long term

A backend LLM/RAG service can answer questions across the archive by retrieving eligible cards and source receipts, citing public article routes, distinguishing quotation from interpretation, and surfacing uncertainty. The UI remains a media network: issues, articles, archives, clusters, and receipts. The backend behaves like cultural intelligence: query understanding, entity resolution, temporal comparison, source-graph traversal, and citation-grounded synthesis.

## Safety and governance

- Preserve original Korean labels/text beside translations.
- Store access and translation limitations with source observations.
- Do not ingest private communities, personal data, or login-gated content without a separate policy and authorization.
- Separate popularity from reliability and community consensus from representative public opinion.
- Make editorial overrides auditable and reversible.
- Keep public indexes public-safe; isolate moderation submissions and abuse signals.
