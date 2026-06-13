# BUILD_PLAN.md — Regulatory Intelligence Agent

## Goal
A governed, demoable multi-agent system on a live public URL, using OpenRouter
for models (free tier). Total running cost: ~$5–10/month (compute only).
Answers a compliance question end-to-end: retrieve context → draft a cited
response → propose an action under human approval.

**Live URL:** https://reg-intel.demo.cloudkraft.com

## Golden workflow
1. A compliance question or regulatory change arrives.
2. **Knowledge Agent** retrieves relevant policy + regulatory text (pgvector RAG).
3. **Analysis Agent** drafts a compliance-grounded, cited response.
4. **Action Agent** proposes a GitHub issue (flag a gap / track an action).
5. **Human approval gate** blocks the write until approved (CLI).
6. Every step traced (LangSmith) and written to the PostgreSQL audit log.

---

## Phase 0 — Accounts, scaffold, decisions ✅ COMPLETE

### Infrastructure decisions (vs. original plan)
- **Model provider:** OpenRouter (not Bedrock) — free `google/gemma-4-31b-it:free`
  for generation; `text-embedding-3-small` for embeddings. Bedrock is the
  production path documented in ADR-005.
- **Database:** Neon free tier PostgreSQL + pgvector (not Railway PostgreSQL plugin)
  — Railway plugin deleted after migration. See ADR-002.
- **GitHub tool:** REST API via `requests` (not MCP Node.js server) — simpler,
  no extra service needed for demo tier.

### Completed
- [x] Railway Hobby account + `reg-intel-agent` project
- [x] `api` service — auto-deploys from `main` branch
- [x] Neon free tier PostgreSQL with pgvector extension
- [x] Custom domain: `reg-intel.demo.cloudkraft.com` (Bluehost CNAME → Railway)
- [x] Repo scaffold: `pyproject.toml`, `src/`, `docker-compose.yml`, `railway.toml`,
      `Dockerfile`, `.env.example`, `.gitignore`, `teardown.sh`
- [x] `terraform/` — `budget_alert.tf` + `iam_bedrock.tf` stubs (AWS not active)
- [x] ADR stubs 001–005 in `docs/adrs/` (renamed with descriptive titles)
- [x] `init-db.sql` — `documents` table (HNSW index) + `audit_log` (append-only triggers)

---

## Phase 1 — Orchestration spine + retrieval (read-only) ✅ COMPLETE

- [x] pgvector HNSW index on Neon PostgreSQL
- [x] LangGraph supervisor + Knowledge Agent + Analysis Agent
- [x] OpenRouter client (ChatOpenAI + OpenAIEmbeddings) using OPENROUTER_API_KEY
- [x] Seed Neon with regulatory docs (GDPR Articles 5/13/17, ISO 27001 Annex A.8)
- [x] Knowledge Agent retrieves via pgvector cosine similarity
- [x] Analysis Agent emits cited response (`[N]` format, `is_cited` flag)
- [x] Citation deduplication by source (same doc cited twice → one entry)
- [x] LangSmith tracing across the full graph
- [x] `tests/test_guardrails.py` + `tests/test_action_agent.py`
- [x] Live at Railway public URL + custom domain

---

## Phase 2 — Action agent + governance layer ✅ COMPLETE

- [x] GitHub tool (`src/tools/github_tool.py`) — REST API issue creation
- [x] Action Agent — proposes JSON `{title, body, labels}`; never executes alone
- [x] Human-in-the-loop gate — `interrupt_before=["human_gate"]` in CLI graph
- [x] Application-level guardrails (`src/guardrails.py`) — denied topics + PII
      Input and output screening; API-compatible with Bedrock Guardrails
- [x] Audit log — append-only `BEFORE DELETE` + `BEFORE UPDATE` triggers
- [x] Citation-mandatory enforcement; `is_cited` flag on every response
- [x] `POST /propose` API endpoint — runs all 3 agents, returns proposal (no execution)
- [x] Per-IP rate limiting — `/query` 10/min 30/day, `/propose` 5/min 15/day
- [x] Tests covering action agent JSON extraction and audit log write
- [x] Live at Railway URL — full workflow demoable

---

## Phase 3 — Harden, package, demo-ready ✅ COMPLETE

- [x] README — setup guide, architecture diagram, governance table, cost section,
      production path, pre-warm note
- [x] Demo UI (`GET /`) — professional single-page HTML explaining architecture,
      governance pillars, pipeline flow, live query form + propose-action demo
- [x] Custom domain resolves: `reg-intel.demo.cloudkraft.com`
- [x] Free model tested and validated: `google/gemma-4-31b-it:free` (citations pass)
- [x] **GitHub Actions CI** — ruff lint + pytest on push to main (23/23 tests green)
- [x] **ADRs** — all 5 written with full substance (interview artifacts)
- [x] **Timeouts + retries** — `urllib3.Retry` on GitHub/Jira tools; `_invoke_with_retry`
      on LLM calls; `_embed_with_retry` on embedding calls
- [x] **Eval harness** — `scripts/eval.py`, 10 fixed compliance questions, 10/10 faithful
- [x] **Demo script** — `docs/demo-script.md`, 3–4 min walkthrough with 5 follow-up Q&As
- [x] **Jira integration** — `src/tools/jira_tool.py`; `TICKET_BACKEND` env var switches
      GitHub ↔ Jira; `/execute` endpoint dispatches accordingly
- [x] **UI HITL** — Approve/Reject buttons on propose result; `/execute` + `/reject`
      endpoints; both decisions written to audit log
- [x] **Email capture** — `/signup` endpoint + `demo_signups` table in Neon
- [x] **Seed documents expanded** — Basel III, OSFI E-23, OSFI B-20, PIPEDA added
      (6 regulatory frameworks, 13 chunks total)

- **Done when:** CI green; ADRs written; live URL works end-to-end; demo script ready. ✅

---

## Production path (out of scope — speak to, don't build)
When there is budget and a real engagement:
- AWS App Runner / ECS Fargate (IAM role replaces OpenRouter key — ADR-005)
- Aurora Serverless v2 with pgvector or OpenSearch Serverless (ADR-002)
- Amazon Bedrock direct (swap OpenRouter client — config-only change)
- AWS Secrets Manager (replaces Railway env vars)
- Private networking, VPC endpoints, WAF
- OSFI E-23 model risk alignment

---

## Stretch (only after Phase 3 is solid)
- [x] Second tool integration — Jira Cloud REST API (done in Phase 3)
- [ ] Azure OpenAI swap path (config-only, shows vendor portability)
- [ ] Bedrock swap (change client + rebuild embeddings at 1024-dim)

---

## ADRs to write (interview artifacts)
1. **LangGraph vs. Amazon Bedrock Agents** — why self-orchestrated; when managed wins
2. **pgvector co-located on Neon (demo) vs. dedicated vector DB (production)** —
   cost delta, what changes, migration trigger
3. **Application guardrails vs. Bedrock Guardrails** — why mirrored API matters;
   production swap path
4. **Railway Hobby (demo) vs. AWS App Runner/ECS (production)** — trade-offs,
   spin-down, production trigger
5. **OpenRouter (demo) vs. Amazon Bedrock (production)** — why OpenRouter for demo;
   how the swap works; IAM access key vs. role

## Demo script (interview — ≈3–4 min)
1. **Problem:** regulated orgs need agents that act, but a monolith can't be audited
2. **Show the UI:** open `reg-intel.demo.cloudkraft.com` — explain the pipeline diagram
3. **Run a query live:** GDPR or ISO 27001 question → show cited response
4. **Run propose:** show Action Agent proposal + HITL gate explanation
5. **Explain governance:** guardrails, audit log, append-only trigger, citation enforcement
6. **Close:** "This runs on Railway Hobby + Neon at effectively zero generation cost —
   free model (Gemma 4 31B via OpenRouter) validated against citation format. In a bank
   this moves to AWS: ECS/App Runner with IAM roles, Bedrock direct, Aurora pgvector,
   private networking, OSFI E-23 alignment. ADR-004 maps that transition exactly."
