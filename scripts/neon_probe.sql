-- Phase 0 read-only probe of the Neon database.
--
-- Reports server/extension capabilities, storage, schema and corpus shape so
-- docs/CURRENT_STATE.md can be completed. It does not read secrets (access
-- codes), email addresses or audit-log payloads; only counts and metadata.
--
-- Run:   psql "$DATABASE_URL" -f scripts/neon_probe.sql > neon_probe.out 2>&1
-- (use the postgresql:// form of the URL, not postgresql+asyncpg://)
--
-- Everything runs inside a READ ONLY transaction and ends with ROLLBACK.

\pset pager off
BEGIN TRANSACTION READ ONLY;

\echo '== 1. Server =='
SELECT version();
SHOW server_version;

\echo '== 2. Extensions installed =='
SELECT extname, extversion FROM pg_extension ORDER BY extname;

\echo '== 3. Extensions available (vector, BM25 / full-text candidates) =='
SELECT name, default_version, installed_version
FROM pg_available_extensions
WHERE name IN ('vector', 'pg_search', 'pg_trgm', 'unaccent', 'pg_bm25', 'rum', 'pgcrypto')
ORDER BY name;

\echo '== 4. Built-in full-text search works (tsvector fallback) =='
SELECT to_tsvector('english', 'Model risk management for federally regulated financial institutions')
       @@ plainto_tsquery('english', 'model risk') AS tsvector_ok;

\echo '== 5. Storage =='
SELECT current_database() AS db,
       pg_size_pretty(pg_database_size(current_database())) AS db_size;
SELECT relname AS table_name,
       n_live_tup AS approx_rows,
       pg_size_pretty(pg_total_relation_size(relid)) AS total_size
FROM pg_stat_user_tables
ORDER BY pg_total_relation_size(relid) DESC;

\echo '== 6. Columns of documents and audit_log =='
SELECT table_name, column_name, data_type, udt_name
FROM information_schema.columns
WHERE table_schema = 'public' AND table_name IN ('documents', 'audit_log')
ORDER BY table_name, ordinal_position;

\echo '== 7. Indexes =='
SELECT tablename, indexname, indexdef
FROM pg_indexes
WHERE schemaname = 'public'
ORDER BY tablename, indexname;

\echo '== 8. Triggers on audit_log, and who could drop them =='
SELECT tgname, tgenabled, pg_get_triggerdef(t.oid) AS definition
FROM pg_trigger t
JOIN pg_class c ON c.oid = t.tgrelid
WHERE c.relname = 'audit_log' AND NOT t.tgisinternal;
SELECT current_user AS connected_as,
       pg_get_userbyid(c.relowner) AS audit_log_owner,
       pg_get_userbyid(c.relowner) = current_user AS app_user_owns_table
FROM pg_class c WHERE c.relname = 'audit_log';

\echo '== 9. Corpus: chunks per title/source, content length =='
SELECT COUNT(*) AS total_chunks, COUNT(DISTINCT source) AS distinct_sources,
       MIN(length(content)) AS min_chars, ROUND(AVG(length(content))) AS avg_chars,
       MAX(length(content)) AS max_chars
FROM documents;
SELECT left(title, 80) AS title, left(source, 60) AS source, length(content) AS chars,
       vector_dims(embedding) AS dims, created_at
FROM documents
ORDER BY id;

\echo '== 10. Duplicate chunks (same title + content) =='
SELECT left(title, 80) AS title, COUNT(*) AS copies
FROM documents
GROUP BY title, md5(content)
HAVING COUNT(*) > 1;

\echo '== 11. Audit log shape (counts only, no payloads) =='
SELECT agent_name, step_type, decision, COUNT(*) AS events,
       MIN(timestamp) AS first_seen, MAX(timestamp) AS last_seen
FROM audit_log
GROUP BY agent_name, step_type, decision
ORDER BY events DESC;

ROLLBACK;
