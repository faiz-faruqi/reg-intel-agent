-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Audit log table (append-only, no deletes permitted)
CREATE TABLE IF NOT EXISTS audit_log (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    agent_name VARCHAR(255),
    step_type VARCHAR(255),
    tool_call VARCHAR(255),
    input JSONB,
    output JSONB,
    decision VARCHAR(255),
    approved BOOLEAN,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Enforce append-only constraint on audit_log (no deletes, no updates)
CREATE OR REPLACE FUNCTION prevent_delete_audit_log()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'Deletes are not permitted on audit_log table';
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER audit_log_prevent_delete
BEFORE DELETE ON audit_log
FOR EACH ROW
EXECUTE FUNCTION prevent_delete_audit_log();

CREATE OR REPLACE FUNCTION prevent_update_audit_log()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'Updates are not permitted on audit_log table';
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER audit_log_prevent_update
BEFORE UPDATE ON audit_log
FOR EACH ROW
EXECUTE FUNCTION prevent_update_audit_log();

-- Documents table for RAG retrieval
-- IMPORTANT: embedding dimension must match the model configured in config.py
--   OpenRouter / OpenAI text-embedding-3-small = 1536
--   AWS Bedrock Titan Embeddings V2              = 1024
--   AWS Bedrock Cohere Embed                     = 1024
-- If switching models, drop and recreate this table + index before seeding data.
CREATE TABLE IF NOT EXISTS documents (
    id SERIAL PRIMARY KEY,
    title VARCHAR(255),
    content TEXT,
    source VARCHAR(255),
    embedding vector(1536),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    -- Full-text search vector, kept in sync automatically — no app-side reindex
    -- step needed on ingest. Powers keyword_search()/hybrid_search() in src/db.py.
    -- See ADR-007 (vector-only vs hybrid retrieval).
    content_tsv tsvector GENERATED ALWAYS AS (
        to_tsvector('english', coalesce(title, '') || ' ' || coalesce(content, ''))
    ) STORED
);

-- HNSW index: works well at any dataset size (unlike IVFFlat which needs ~hundreds of rows).
-- Demo doc set (~20-50 docs) would be slower with IVFFlat. See ADR-002.
CREATE INDEX IF NOT EXISTS documents_embedding_idx ON documents USING hnsw (embedding vector_cosine_ops);

-- GIN index for keyword search (RETRIEVAL_MODE=hybrid). See ADR-007.
CREATE INDEX IF NOT EXISTS documents_content_tsv_idx ON documents USING gin (content_tsv);

-- Demo visitor email capture
CREATE TABLE IF NOT EXISTS demo_signups (
    id         SERIAL PRIMARY KEY,
    email      VARCHAR(255) NOT NULL,
    ip_address VARCHAR(45),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
