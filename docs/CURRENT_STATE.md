# Current State — Regulatory Intelligence Agent (Phase 0 baseline)

**Baseline commit:** `63fcb80` on `main` (tag `baseline-v0`), the code running at
`https://reg-intel.demo.cloudkraft.com`.
**Recorded:** 2026-10-16, Phase 0 of `docs/PLAN_v2.md`.
**Method:** read the repository, ran lint, tests and the mock eval locally, and validated a read-only
database probe against a local Postgres 16 + pgvector. The live Neon database was **not** queried from
this environment; section 9 is filled from `scripts/neon_probe.sql` once Faiz runs it.

Status labels used below: `Implemented` (in code), `Tested` (covered by an automated test),
`Designed` (described, not built), `Planned`, and `Gap` (claimed in docs but not true in code).

---

## 1. Summary

The system is a working three-agent LangGraph pipeline behind FastAPI, with pgvector retrieval,
an append-only audit log, a signed-cookie login gated by a time-limited access code, per-IP and
per-session rate limits, and a web UI with Approve/Reject buttons. Lint and all 43 unit tests pass.

The baseline is weaker than the docs suggest in five places that matter for the plan:

1. **Guardrails do not run on the API path.** `check_input` / `check_output` are called only in
   `src/cli.py`. `/query` and `/propose` (what the live UI uses) skip them.
2. **The UI approval gate is not bound to the agent's proposal.** `/execute` creates a ticket from
   whatever `title`, `body` and `labels` the browser sends. Any signed-in user can create an arbitrary
   GitHub issue, and nothing records which proposal was approved.
3. **Rate limits are probably shared by all visitors.** uvicorn runs without proxy-header trust, so
   `get_remote_address` most likely sees Railway's proxy address, not the visitor's. To be confirmed.
4. **The seed corpus is authored summaries, not official regulatory text.** 15 chunks of 2.6–5.7k
   characters; several "OSFI E-23" chunks (third-party models, climate, ICAAP) are synthesised topic
   summaries. B-10 and B-13 are absent.
5. **Retrieval cannot be reproduced from the audit log.** It records source strings and counts, not
   chunk IDs, prompt version, model ID or a request ID.

None of these is a Phase 0 fix (Phase 0 makes no functional changes). Section 12 proposes how to
handle them.

---

## 2. Architecture as built

```
Browser ──► FastAPI (Railway Hobby, 1 uvicorn worker, sleeps after 30 min)
              │  auth: signed cookie (itsdangerous) + username/password + single active access code
              │  limits: slowapi per-IP  +  session_usage table (15 metered actions per login)
              ├─ /query   → graph:          supervisor → knowledge_agent → analysis_agent
              ├─ /propose → propose_graph:  supervisor → knowledge → analysis → action_agent
              ├─ /execute → github_tool | jira_tool   (TICKET_BACKEND)
              └─ /reject  → audit_log
            CLI (python -m src.cli): guardrails in → graph → guardrails out → interrupt_before human_gate
              │
              ├─► OpenRouter  (chat: GENERATION_MODEL; embeddings: text-embedding-3-small, 1536-d)
              ├─► Neon Postgres + pgvector  (documents, audit_log, demo_signups, session_usage, access_code)
              ├─► LangSmith (tracing via env vars)
              └─► GitHub REST / Jira Cloud REST
```

- **Provider abstraction:** `src/llm.py` builds chat and embedding clients for `openrouter`,
  `azure_openai` (ADR-006) or `bedrock` from `MODEL_PROVIDER`.
- **Graph:** two compiled graphs in `src/graph.py` (read-only and propose). The supervisor is a
  deterministic router, not an LLM. The CLI builds a third graph with a `MemorySaver` checkpointer
  and `interrupt_before=["human_gate"]`.
- **Execution model:** route handlers are `async def` but call the synchronous `graph.invoke`, which
  does blocking psycopg2 queries, HTTP calls and `time.sleep` retries. While one request runs, the
  single worker cannot serve another, `/health` included.

## 3. Stack and versions

| Component | Declared (`pyproject.toml`) | Resolved in a fresh install today |
|---|---|---|
| Python | `>=3.11` (Dockerfile and CI: 3.11) | 3.13 used for this local run |
| FastAPI | `>=0.104.0` | 0.143.2 |
| uvicorn | `>=0.24.0` | 0.54.0 |
| LangGraph | `>=0.0.20` | 1.2.15 |
| LangChain / core / openai | `>=0.1.0` / — / `>=0.0.5` | 1.4.6 / 1.6.11 / 1.7.2 |
| LangSmith | `>=0.0.75` | 0.14.9 |
| pgvector (py) | `>=0.1.0` | 0.5.1 |
| psycopg2-binary | `>=2.9.0` | 2.9.13 |
| slowapi | `>=0.1.9` | 0.1.10 |
| pydantic | `>=2.0.0` | 2.14.1 |
| ruff / black / pytest | `>=0.1.0` / `>=23.0` / `>=7.4` | 0.17.1 / 26.10.1 / 9.1.1 |
| RAGAS (evaluation/ only) | `==0.2.10` | not installed (mock mode only) |

There is no lockfile. Every Docker build resolves the newest versions allowed, so two builds of the
same commit can differ. Eval runs cannot pin their dependency set until this changes (Phase 2).

## 4. API surface

| Route | Auth | Rate limit (per IP) | Notes |
|---|---|---|---|
| `GET /` | session | — | Demo UI; redirects to sign-in |
| `GET/POST /auth/signin` | — | POST 5/min, 15/day | username + password + access code |
| `POST /auth/generate-code` | `X-Admin-Key` | none | Replaces the single active code |
| `POST /auth/signout` | — | — | Clears cookie |
| `GET /health` | — | — | Static `{"status":"ok"}`; does not check the DB |
| `GET /mra-report.pdf` | none | — | Static PDF |
| `POST /query` | session + budget | 10/min, 20/day | Knowledge + Analysis; **no guardrails** |
| `POST /propose` | session + budget | 5/min, 10/day | All three agents; returns the proposal; **no guardrails** |
| `POST /execute` | session | 2/min, 5/day | Creates the ticket from the client-supplied body |
| `POST /reject` | session | 5/min, 10/day | Audit only |
| `POST /signup` | none | 1/min, 3/day | Stores email + IP; no email validation |
| `GET /docs` | none | — | Swagger UI |

`top_k` on `/query` and `/propose` is taken from the client without an upper bound. Today the corpus
caps it at 15 chunks; after Phase 1 it would let a caller inflate prompt size and cost.

## 5. Data model

Defined in `init-db.sql`:

- `documents(id, title, content, source, embedding vector(1536), created_at)` with an HNSW cosine
  index. No document ID, version, section path, effective date, chunk hash or ACL columns.
- `audit_log(id, timestamp, agent_name, step_type, tool_call, input jsonb, output jsonb, decision,
  approved, created_at)` with `BEFORE DELETE` and `BEFORE UPDATE` triggers that raise. No hash chain,
  request ID or actor identity. Tampering is prevented for a normal connection but not detectable:
  the table owner can disable or drop the triggers (probe section 8 shows whether the app user owns
  the table).
- `demo_signups(id, email, ip_address, created_at)`.

Created at runtime by `src/db.py`, not in `init-db.sql`:

- `session_usage(sid, action_count, created_at, updated_at)`.
- `access_code(id=1, code, expires_at, created_at)`, a single row with the code stored in plain text.

There is no migration tool. Schema changes so far have been `CREATE TABLE IF NOT EXISTS` in SQL or
in application code.

## 6. Agents and prompts

| Agent | What it does | Audit record |
|---|---|---|
| Knowledge | Embeds the question (3 retries), cosine top-k from `documents`, no similarity threshold | `retrieval`: question, top_k, count, source strings |
| Analysis | Inline `SYSTEM_PROMPT`; formats chunks as `[N] title (Source)`; maps `[N]` markers back to sources; `is_cited = any valid marker found` | `generation`: question, chunk count, response length, citations count, `is_cited` |
| Action | Proposes `{title, body, labels}` JSON | Proposal |

- Prompts are inline Python strings, not versioned files.
- No abstention path: the agent always answers from the top-k chunks and relies on the model to
  decline. `is_cited` checks that a marker exists, not that the cited chunk supports the claim.
- Guardrails (`src/guardrails.py`): 7 denied-topic substrings on input; output PII regexes for a
  **US** SSN, card numbers and email addresses. A Canadian SIN is not detected.

## 7. Governance controls: claimed vs actual

| Control (from `CLAUDE.md`) | Status | Evidence |
|---|---|---|
| Input/output guardrails | `Implemented` and `Tested` in the CLI; **`Gap` on the API** | `tests/test_guardrails.py`; no call in `src/main.py` or `src/graph.py` |
| Human-in-the-loop | `Implemented` in the CLI (interrupt); **`Gap` in the UI**: approval not bound to a proposal | `/execute` accepts any body |
| Append-only audit log | `Implemented` (triggers); tamper-detection `Planned` (Phase 5) | `init-db.sql` |
| Every step and approval audited | Partial: `/execute` writes the audit row **after** creating the ticket, so if that write fails the ticket exists with no audit record and a retry duplicates it | `src/main.py` `/execute` |
| Citations mandatory | `Implemented` as marker presence; support check `Planned` (R6) | `analysis_agent.py` |
| Rate limiting | `Implemented`; per-visitor effect **unverified** (proxy IP) | no `--proxy-headers` / `FORWARDED_ALLOW_IPS` in `Dockerfile` or `railway.toml` |
| Session action budget | `Implemented` and `Tested` | `session_usage`, `tests/test_access_code.py` |
| Tracing | `Implemented` via env vars; not verified from here | `.env.example` |

## 8. Corpus inventory (from `data/seed_documents.json` and `src/ingest.py`)

`src/ingest.py` loads 15 entries from `data/seed_documents.json` **plus**
`docs/seed-data/cloudkraft-ai-governance.txt`, so a clean run stores **16** rows, not the 15 the docs
state. Re-running inserts duplicates; ingest only logs a warning.

| # | Title (abridged) | Chars | Kind |
|---|---|---|---|
| 1 | GDPR Articles 5, 13, 17 | 4,008 | Summary |
| 2 | ISO/IEC 27001:2022 Annex A.8 | 2,599 | Summary |
| 3 | Basel III capital, liquidity, leverage | 3,923 | Summary |
| 4 | OSFI E-23 Model Risk Management (2025 final, eff. 2027-05-01) | 5,680 | Summary of the guideline |
| 5 | OSFI B-20 Residential Mortgage Underwriting | 4,357 | Summary |
| 6 | "OSFI E-23 — Third-Party and Vendor Model Risk (2024)" | 3,975 | Synthesised topic note |
| 7 | "OSFI E-23 — Model Risk Appetite, Rating, Inventory (2024)" | 3,604 | Synthesised topic note |
| 8 | "OSFI E-23 — Supervisory Review Expectations (2024)" | 3,302 | Synthesised topic note |
| 9 | "OSFI E-23 — ICAAP Models and Stress Testing (2024)" | 2,780 | Synthesised topic note |
| 10 | "OSFI E-23 — Climate Risk Models (2024)", read with B-15 | 3,337 | Synthesised topic note |
| 11 | PIPEDA key principles | 5,164 | Summary |
| 12 | NIST AI RMF core functions | 3,193 | Summary |
| 13 | EU AI Act risk classification | 3,362 | Summary |
| 14 | ISO/IEC 42001 AIMS | 2,884 | Summary |
| 15 | AI Governance Principles (CloudKraft synthesis) | 4,336 | Authored reference |
| 16 | CloudKraft AI Governance diagnostic (HTML → text) | — | Authored reference |

Observations:
- None of the rows is verbatim official text, and no row records a URL, version or section. The
  2024-labelled E-23 notes cite the 2025 final guideline as their source, which is inconsistent.
- Under the plan's "no fabricated regulatory text" rule, Phase 1 replaces the OSFI rows with official
  text and keeps the rest only if they are labelled as summaries.
- One chunk per document means the chunker has never split anything; "structure-aware chunking" in
  Phase 1 is new behaviour, not a change to existing behaviour.

## 9. Live database (pending Faiz's probe run)

Run `psql "$DATABASE_URL" -f scripts/neon_probe.sql > neon_probe.out 2>&1` and paste the output here.
It answers:

- [ ] Postgres and pgvector versions
- [ ] Whether `pg_search` (BM25) is available, or only built-in `tsvector`
- [ ] Database size against the Neon free-tier limit
- [ ] Actual chunk count (15 or 16) and whether duplicates exist
- [ ] Whether the app user owns `audit_log` (can drop its triggers)
- [ ] Audit-log volume by agent and step

## 10. Evaluation as it stands

- `scripts/eval.py`: 10 fixed questions, scores `cited`, `source_hit`, `faithful`. Needs a live key.
- `evaluation/` (RAGAS assurance framework): 15 golden items:
  5 OSFI E-23, 4 AI governance, 2 NIST AI RMF, 1 EU AI Act, 1 ISO 42001 (all answerable) and 2
  out-of-scope. Ground truths are "concise, original summaries", flagged in the dataset itself as
  needing SME review before use as evidence.
- **Mock run today** (`python run_assurance.py --mode mock`): faithfulness 0.860, answer relevancy
  0.906, context precision 0.866, context recall 0.852, refusal correctness 1.0. These come from
  deterministic **synthetic** responses and measure nothing about the agent. The UI labels them
  "mock run", which is accurate. No live baseline was run in Phase 0 (no API key in this environment).
- Two harnesses, no retrieval metrics (Recall@k, MRR), no latency or cost capture, no pinned run
  config, no committed run folders.

## 11. Tests, lint and CI

| Check | Result |
|---|---|
| `ruff check src/ tests/` | All checks passed |
| `pytest` | **43 passed** (docs say 23): access code 12, retrieval 12, guardrails 8, LLM provider 6, action agent 4, health 1 |
| `black --check src tests` | 14 files would be reformatted. `CLAUDE.md` names black, but CI does not run it |
| mypy | Configured, not run in CI |
| CI (`.github/workflows/ci.yml`) | Python 3.11, `pip install -e .[dev]`, ruff, pytest. All mocked; no eval, security or type check |

## 12. Known gaps, ranked

| # | Gap | Severity | Proposed handling |
|---|---|---|---|
| 1 | Guardrails not applied on `/query` and `/propose` | High: live behaviour contradicts the docs | Hotfix (see below) or Phase 5 |
| 2 | `/execute` trusts the client body; approval not bound to a proposal | High | Hotfix: `/propose` returns a signed proposal token, `/execute` accepts only that token. Full fix in Phase 5 (policy + outbox) |
| 3 | Ticket created before its audit row; no idempotency | Medium | Phase 5, R5 outbox |
| 4 | Rate limits likely keyed on the proxy IP | Medium: one visitor can use up the daily limit for everyone | Hotfix: run uvicorn with `--proxy-headers --forwarded-allow-ips` set for Railway, after confirming in logs |
| 5 | Sync graph inside async handlers blocks the worker | Medium | Phase 7 (run in a thread pool) |
| 6 | Confirm `SESSION_SECRET`, `DEMO_PASSWORD`, `ADMIN_KEY` are set in Railway; the code defaults are public | High if unset: a known secret lets anyone forge a session and skip the access code | Faiz checks Railway env (no code change) |
| 7 | Unbounded `top_k` | Low now, Medium after Phase 1 | Phase 2 (typed request contract) |
| 8 | `/execute` returns raw exception text to the client | Low | Hotfix or Phase 7 |
| 9 | Access code stored in plain text; admin key and code compared with `==` | Low | Phase 5 |
| 10 | US-only PII patterns (no SIN) | Low | Phase 5 |
| 11 | No lockfile; floating dependency versions | Medium for reproducibility | Phase 2 |
| 12 | No migrations; runtime `CREATE TABLE` | Medium | Phase 1 (numbered SQL migrations with a `schema_migrations` table) |
| 13 | Corpus is summaries with no provenance; ingest not idempotent | High for the plan | Phase 1 |
| 14 | Audit log has no request ID, chunk IDs, model or prompt version | Medium | Phase 5, R4 decision record |

## 13. Where the plan's assumptions don't match the repo

In addition to the seven items in `docs/PLAN_v2.md` section A1:

1. Guardrails and the approval gate are weaker on the API path than the plan assumes (gaps 1 and 2).
   Phase 5 builds on controls that are partly missing, not on finished ones.
2. The corpus has no official text at all, not "E-23 in a few chunks". Phase 1 sources all three OSFI
   guidelines from scratch.
3. The test count is 43, not 23. CI is green.
4. A clean ingest stores 16 rows, not 15.
5. There is no migration mechanism. Phase 1 must add one before any schema change.
6. Dependencies float. Phase 2's "pin the configuration per run" needs a lockfile first.
7. ADR numbering: `evaluation/docs/adr/ADR-006-ai-assurance-framework.md` collided with
   `docs/adrs/ADR-006-azure-openai-as-alternate-provider.md`. **Resolved in Phase 0:** renamed to
   ADR-007, references in `evaluation/` updated, row added to the README ADR table. Next free is ADR-008.

## 14. Proposed doc updates (for approval, not applied)

**`BUILD_PLAN.md`:** add a section after "Stretch":

> ## Phase 4+ — Evidence-backed flagship (in progress)
> Governed by `docs/PLAN_v2.md`: phases 0–10 (4a/4b canonical layer, crosswalk, applicability;
> change-impact mode; evidence page). Items listed there count as in scope for the
> "flag anything not in BUILD_PLAN.md" rule.

and correct stale facts: generation model is `GENERATION_MODEL` (`z-ai/glm-5.2` in the live env),
not the free Gemma; rate limits are `/query` 10/min 20/day and `/propose` 5/min 10/day; tests 43;
16 seeded rows.

**`CLAUDE.md`:** tests 43 (not 23); 16 seeded rows; note that guardrails currently run only in the
CLI until gap 1 is fixed; ADR count 7.

## 15. Decisions needed before Phase 1

1. **Hotfix for gaps 1, 2, 4 and 8:** a small PR on its own branch (`hotfix-api-governance`) before
   Phase 1? It is a functional change to the live demo, so it needs your approval and a deploy you
   trigger. Recommended: yes, because the demo currently claims controls the API does not apply.
2. **Gap 6:** please confirm in Railway that `SESSION_SECRET`, `DEMO_PASSWORD` and `ADMIN_KEY` are set
   to non-default values. No code change.
3. **Doc updates in section 14:** apply as proposed?
4. **Probe output:** run `scripts/neon_probe.sql` and paste the result so section 9 can be completed.
