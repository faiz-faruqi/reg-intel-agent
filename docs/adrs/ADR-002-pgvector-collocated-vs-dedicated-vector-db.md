# ADR-002: pgvector Co-located (Demo) vs. Dedicated Vector DB (Production)

## Status
Accepted

## Date
2026-06-05

## Context

The Regulatory Intelligence Agent requires a vector store for RAG retrieval over
policy and regulatory documents. Two credible options exist at demo scale:

**Option A — pgvector on the existing Railway PostgreSQL instance**
The Railway PostgreSQL plugin already provides the relational store for the audit
log. pgvector is a PostgreSQL extension that adds a `vector` column type and
approximate-nearest-neighbour (ANN) index operators (`hnsw`, `ivfflat`). Enabling
it costs nothing beyond the compute already budgeted.

**Option B — Dedicated vector database (Qdrant, Weaviate, Pinecone, or
OpenSearch Serverless)**
Purpose-built vector databases offer higher query throughput, built-in sharding,
richer metadata filtering, and managed ANN index tuning. They are the right
choice once the document corpus exceeds tens of thousands of chunks or query
latency becomes a product constraint.

The demo corpus is small: 20–50 regulatory and policy documents (~100–200
chunks after splitting). Query volume is interview-demo traffic only. The
Railway Hobby tier already pays for a PostgreSQL instance; adding a second
managed vector service would add CAD $25–80/month (Qdrant Cloud free tier
exhausted at ~1 M vectors; Pinecone Starter limits concurrent queries; OpenSearch
Serverless has a minimum OCU cost of ~USD $24/month even at zero traffic).

## Decision

Use **pgvector on the co-located Railway PostgreSQL instance** for the demo tier.

Configure an **HNSW index** (not IVFFlat) on the `documents.embedding` column.
HNSW builds incrementally and performs well at any dataset size; IVFFlat requires
a minimum number of training rows (~hundreds) before the index outperforms a
sequential scan. At demo scale, IVFFlat would actually be slower.

```sql
CREATE INDEX documents_embedding_idx
ON documents USING hnsw (embedding vector_cosine_ops);
```

Embedding model for Phase 1: OpenAI `text-embedding-3-small` (1536 dimensions).
Embedding model for Phase 2 (Bedrock): Titan Embeddings V2 (1024 dimensions).
The `vector(N)` column dimension must match the model. Changing models requires
a full table rebuild — lock the choice before seeding data.

## Consequences

### What this buys
- **Zero additional cost** at demo scale. Total AWS + Railway spend stays under
  CAD $35/month.
- **Operational simplicity**: one connection string, one service to manage, one
  backup to configure. The audit log and the vector store share the same
  PostgreSQL transaction boundary — a future migration could write a document
  embedding and its audit record atomically.
- **Sufficient performance**: pgvector HNSW delivers sub-10 ms similarity search
  on a 200-chunk corpus. That is faster than the Bedrock model invocation that
  follows it.
- **Honest demo story**: the architectural trade-off is visible and explainable.
  Interviewers respond well to "I made a deliberate cost decision and I know
  exactly when it stops being the right call."

### What this costs (accepted trade-offs)
- **No horizontal scaling**: pgvector runs inside a single PostgreSQL instance.
  Once the corpus reaches ~500 K chunks or QPS exceeds ~50 concurrent similarity
  searches, connection pooling and query latency will degrade.
- **No built-in metadata filtering at index time**: pgvector filters are applied
  post-scan, not pre-scan. Complex `WHERE` clauses on metadata columns reduce the
  ANN benefit at scale. Dedicated vector DBs (Qdrant, Weaviate) push filters into
  the index.
- **Shared I/O with audit log**: heavy ingestion and heavy audit writes contend
  for the same PostgreSQL I/O budget. Acceptable at demo scale; a concern at
  production volume.
- **Index rebuild on model swap**: changing the embedding model (e.g., Phase 1 →
  Phase 2 Bedrock) requires dropping the table, recreating with the new dimension,
  and re-ingesting all documents. Not zero-cost but acceptable for a planned
  migration.

## Production trigger

Migrate to a dedicated vector store when **any one** of the following is true:

1. The document corpus exceeds **50 K chunks** (pgvector HNSW recall degrades
   without careful `m` / `ef_construction` tuning, and index build time becomes
   a maintenance window concern).
2. Similarity search P99 latency exceeds **200 ms** under production query load.
3. The application requires **pre-filter ANN search** (e.g., filter by
   `jurisdiction = "OSFI"` before the vector scan, not after).
4. The audit log and vector store need **independent scaling** or **separate
   backup/retention policies** for compliance reasons.

## Production path (out of scope for this phase)

When the trigger is hit:

| Concern | Demo (now) | Production |
|---|---|---|
| Vector store | pgvector on Railway PostgreSQL | pgvector on Aurora Serverless v2, **or** OpenSearch Serverless (k-NN), **or** Pinecone Enterprise |
| Audit log | Same PostgreSQL instance | Separate RDS/Aurora instance with point-in-time recovery |
| Index type | HNSW (pgvector) | HNSW (pgvector) or HNSW/IVF (OpenSearch) |
| Embedding dimensions | 1536 (Phase 1) / 1024 (Phase 2) | Same — locked before migration |
| Cost delta | $0 additional | ~USD $50–200/month depending on corpus size and query volume |

**Aurora Serverless v2 with pgvector** is the preferred production path if the
corpus stays under ~5 M chunks: it keeps the pgvector API (no client change),
adds autoscaling, and stays inside AWS private networking. OpenSearch Serverless
is preferred if metadata filtering and faceted search become first-class
requirements (e.g., filtering by regulation number, jurisdiction, or effective
date before the ANN scan).

## References
- [pgvector HNSW documentation](https://github.com/pgvector/pgvector#hnsw)
- ADR-004 — Railway Hobby vs. AWS App Runner/ECS (hosting transition trigger)
