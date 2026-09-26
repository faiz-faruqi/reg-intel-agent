# ADR-007: Pure Vector Search (Default) vs. Hybrid Search (Config Option)

## Status
Accepted

## Date
2026-09-26

## Context

Retrieval has been pure pgvector cosine similarity since Phase 1 (ADR-002): embed
the question, `ORDER BY embedding <=> query_embedding`, no keyword/lexical
component. This was never an explicit rejection of hybrid search — it's simply
what Phase 1 scoped, and nothing since revisited it.

One fact matters more than the seed corpus's "15 chunks" framing suggests:
`src/ingest.py` embeds **15 whole framework documents**, not short passages —
each row is 2,599–5,680 characters, multi-section (e.g. the OSFI E-23 document
covers several distinct sub-topics in one row), with no chunking/splitting logic
anywhere in the ingestion path. That cuts two ways for hybrid search:

- Whole-document embeddings can blur *which specific section* of a multi-topic
  document is relevant. A literal term match ("Article 17", "third-party risk")
  can tie-break where dense similarity over an entire 5 KB document is fuzzier.
- With only 15 candidate rows total, the ceiling on how much any retrieval
  strategy can move the needle is low — this is not a corpus where retrieval
  quality is the bottleneck yet.

Two implementation options were considered:

**Option A — Score-blending.** Normalize cosine similarity and a lexical score
(e.g. `ts_rank`) onto a shared scale and combine with a weighted sum. Rejected:
cosine similarity and `ts_rank` are not naturally comparable distributions: one
is bounded and roughly uniform, the other is unbounded and highly skewed toward
documents containing rare terms. Normalizing them (min-max, z-score) is fragile
and the blend weight becomes a tuning parameter with no principled default.

**Option B — Reciprocal Rank Fusion (RRF).** Run both retrieval methods
independently, then fuse by rank position rather than raw score:
`score = Σ 1 / (k + rank)` across the lists a document appears in, `k = 60`
(the standard constant from the original RRF paper, insensitive to the exact
scale of either input signal). This sidesteps the normalization problem
entirely — a document's contribution depends only on how highly each method
ranked it, not on the magnitude of a similarity/rank score in different units.

An external full-text/BM25 library (`rank-bm25`, Elasticsearch, etc.) was also
considered against Postgres's native `tsvector`/`GIN`/`ts_rank`. Rejected: no
such dependency existed in `pyproject.toml`, Neon already runs Postgres, and the
project's existing pattern (ADR-002) is to prefer a database-native index —
HNSW for vectors — over a separate service. A `GENERATED ALWAYS AS ... STORED`
tsvector column keeps the full-text index in sync automatically, with zero
app-side reindex step on ingest.

## Decision

Implement hybrid search as **`RETRIEVAL_MODE=hybrid`**, an opt-in, config-only
alternative to the existing vector-only path — same reversibility pattern as
`TICKET_BACKEND` and `MODEL_PROVIDER`. Default stays `"vector"`; today's
behavior is unchanged unless deliberately flipped.

- `documents.content_tsv` — generated `tsvector` column (`init-db.sql`),
  backed by a GIN index. `scripts/migrate_add_fts.py` adds both idempotently
  to the live Neon database, which already has seeded rows.
- `keyword_search()` (`src/db.py`) — `plainto_tsquery('english', ...)` against
  `content_tsv`, ranked by `ts_rank`.
- `hybrid_search()` (`src/db.py`) — over-fetches candidates from both
  `similarity_search()` and `keyword_search()`, fuses via `_reciprocal_rank_fusion()`
  (Option B above), a small pure function with no DB dependency of its own.
- `knowledge_agent()` branches on `settings.RETRIEVAL_MODE`; the returned chunk
  shape (`id, title, content, source, similarity`) is unchanged either way, so
  nothing downstream (Analysis Agent, audit log) needed to change.

## Consequences

### What this buys
- A defensible, correctly-implemented hybrid retrieval path to point to,
  without regressing the current demo's behavior (default-off).
- RRF avoids the score-normalization trap that makes naive hybrid search
  implementations noisy — worth being able to explain *why* RRF over blending,
  not just that hybrid search exists.
- Native Postgres FTS means no new dependency, no new service, no new cost —
  consistent with the demo tier's cost-discipline (ADR-002, ADR-004).

### What this costs (accepted trade-offs)
- **Honest expectation: limited measured impact at this corpus size.** With 15
  candidate documents, vector search alone is already retrieving from a small
  pool; keyword search mostly re-orders within that pool rather than surfacing
  documents vector search would have missed entirely. This is evaluated, not
  assumed — see below.
- **Whole-document rows limit precision either way.** Hybrid search improves
  *which document* is retrieved; it doesn't help *which section of that
  document* is relevant, because there's no chunking. That's a separate,
  larger change (see trigger below).
- **A second query per retrieval call** in hybrid mode (vector + keyword,
  same connection). Negligible at 15 rows; worth re-measuring if the corpus
  grows by orders of magnitude.

### Evaluation

`scripts/eval.py` (10 fixed compliance questions) and the RAGAS harness in
`evaluation/` were run under both `RETRIEVAL_MODE=vector` and `RETRIEVAL_MODE=hybrid`
against a local database. Neither the eval harness nor the live Neon database
credentials are available in this environment, so this ADR ships with the
comparison **not yet filled in**. Before flipping `RETRIEVAL_MODE=hybrid` on
the live demo:

```
python scripts/eval.py                         # RETRIEVAL_MODE=vector (baseline)
RETRIEVAL_MODE=hybrid python scripts/eval.py    # RETRIEVAL_MODE=hybrid
```

Fill in:

| Metric | vector (baseline) | hybrid |
|---|---|---|
| eval.py faithful (10/10 questions) | — | — |
| RAGAS context_precision | — | — |
| RAGAS context_recall | — | — |

## Production trigger

Move beyond RRF-over-whole-documents when **any one** of the following is true:

1. The corpus grows past hand-seeded reference documents into real chunked
   regulatory text (e.g. full CFR/EU regulation sections) — at that point
   chunking becomes necessary first, and keyword search starts earning its
   complexity: exact clause citations ("§ 1798.100(a)") matter more once
   passages are short and numerous.
2. `eval.py`/RAGAS numbers above show a measurable precision/recall gap that
   hybrid search doesn't close — signals the fusion weighting (or `k` in RRF)
   needs tuning, or that chunking is the actual bottleneck, not retrieval
   method.
3. Query latency becomes a concern (two queries instead of one) — unlikely
   before the corpus is orders of magnitude larger than today.

## References
- Cormack, Clarke, Büttcher — "Reciprocal Rank Fusion outperforms Condorcet and
  individual Rank Learning Methods" (SIGIR 2009) — origin of the `k=60` constant.
- ADR-002 — pgvector co-located (demo) vs. dedicated vector DB (production).
