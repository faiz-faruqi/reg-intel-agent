# BUILD_PLAN.md — Regulatory Intelligence Agent (Bedrock + Railway Hobby)

## Goal
A governed, demoable multi-agent system on a live public Railway URL, calling
Amazon Bedrock for models. Total running cost: ~CAD $20–35/month.
Answers a compliance question end-to-end: retrieve context → draft a cited
response → propose an action under human approval.

## Golden workflow
1. A compliance question or regulatory change arrives.
2. **Knowledge Agent** retrieves relevant policy + regulatory text (pgvector RAG).
3. **Analysis Agent** drafts a compliance-grounded, cited response.
4. **Action Agent** proposes a write (flag a gap / create a ticket via MCP).
5. **Human approval gate** blocks the write until approved.
6. Every step traced (LangSmith) and written to the PostgreSQL audit log.

## Reuse from existing portfolio
- Regulatory Intelligence Platform → domain framing, governance patterns,
  citation and audit scaffolding
- LangGraph orchestration → supervisor + agent graph + HITL gates
- Swap model layer to Bedrock; swap vector store to pgvector

---

## Phase 0 — Accounts, scaffold, decisions (≈3–4 hrs)

### AWS (minimal — models only)
- [ ] AWS account + enable Bedrock model access (Claude Sonnet + Haiku + embeddings)
      in ca-central-1
- [ ] **Deploy `terraform/budget_alert.tf` FIRST** — $30/mo ceiling on Bedrock spend
- [ ] Deploy `terraform/iam_bedrock.tf` — minimal IAM user, Bedrock invoke only
      Copy the output access key values → Railway env vars + local .env
      Record as ADR-005: IAM access key (demo/Railway) vs. IAM role (production/AWS)

### Railway
- [ ] Create Railway account — **Hobby tier** ($0 base, compute-only billing)
- [ ] New Railway project: `reg-intel-agent`
- [ ] Add TWO services only:
      1. `api` — from GitHub repo (auto-deploy on push to main)
      2. `postgres` — Railway PostgreSQL plugin with pgvector extension enabled
- [ ] Set env vars in Railway dashboard (see .env.example)
- [ ] Note the Railway-provided public HTTPS URL for the api service

### Repo scaffold (new repo — NOT inside the-institutional-brain)
- [ ] New repo: `reg-intel-agent`
- [ ] Drop CLAUDE.md and BUILD_PLAN.md at repo root
- [ ] `pyproject.toml` — Python 3.11+, ruff, black, pytest, FastAPI, LangGraph,
      LangChain, boto3, psycopg2-binary, pgvector, asyncpg
- [ ] `src/` directory structure with empty `__init__.py` files
- [ ] `.env.example` — all required env vars, no values
- [ ] `.gitignore` — Python + .env + Terraform state
- [ ] `docker-compose.yml` — FastAPI + PostgreSQL with pgvector for local dev
      (mirrors the Railway setup exactly)
- [ ] `railway.toml` — build + deploy config
- [ ] `Dockerfile` — multi-stage, non-root user, health check at /health
- [ ] `terraform/` — budget_alert.tf + iam_bedrock.tf
- [ ] `docs/adrs/` — ADR stubs 001–005
- [ ] `teardown.sh` at repo root

- **Done when:** `docker compose up` runs locally with pgvector; Railway project
  exists with two services; budget alert + IAM user deployed via Terraform.

---

## Phase 1 — Orchestration spine + retrieval (read-only) (Weekend 1)

- [ ] Enable pgvector extension on Railway PostgreSQL:
      `CREATE EXTENSION IF NOT EXISTS vector;`
- [ ] LangGraph supervisor + Knowledge Agent + Analysis Agent (no Action Agent)
- [ ] Bedrock client (boto3) using IAM access key from env vars — NO hardcoded keys
- [ ] Seed PostgreSQL/pgvector with a small policy/regulatory doc set
- [ ] Knowledge Agent retrieves via pgvector; Analysis Agent emits a cited answer
- [ ] Bedrock embeddings for ingestion (Titan or Cohere); Claude Sonnet for generation
- [ ] LangSmith tracing across the full graph
- [ ] At least one pytest test for the retrieval + draft flow
- [ ] Push to main → Railway auto-deploys → test against the live URL

- **Done when:** question in → cited answer out, read-only, traced, one test green,
  working at the Railway public URL.

---

## Phase 2 — Action agent + governance layer (Weekend 2) — the money demo

- [ ] Add one MCP server (GitHub or Jira) and the Action Agent
- [ ] Human-in-the-loop approval gate (CLI prompt)
- [ ] **Bedrock Guardrails** — content filters, denied topics, PII handling
- [ ] Audit table in PostgreSQL (append-only): every step, tool call, decision,
      approval — schema enforces no deletes
- [ ] Citation-mandatory enforcement; prompt-injection handling on retrieved content
- [ ] IAM scoping verified: Bedrock calls use only the allowed model ARNs
- [ ] Tests covering approval gate and audit log write
- [ ] Push to main → Railway deploys → golden workflow live at public URL

- **Done when:** full workflow runs; no write without approved, audited human decision;
  Guardrails active; green tests; live at Railway URL.

---

## Phase 3 — Harden, package, demo-ready (Weekend 3)

- [ ] Timeouts, retries, circuit breakers on every Bedrock/MCP call; cost ceiling
- [ ] Eval harness: 5–10 fixed cases, faithfulness + task success scored
- [ ] GitHub Actions CI: tests + eval on push; ruff lint
- [ ] README: setup guide, live demo URL, cost section, pre-warm note
- [ ] Complete all 5 ADRs (see below)
- [ ] Demo script / recorded walkthrough ready
- [ ] Set up `demo.cloudkraft.com` CNAME → Railway URL via Bluehost DNS

- **Done when:** CI green; live URL works end-to-end; README complete; ADRs written;
  custom domain resolves.

---

## Production path (out of scope — speak to, don't build)
When there is budget and a real engagement:
- AWS App Runner / ECS Fargate (IAM role replaces access key — ADR-005)
- Aurora Serverless v2 with pgvector or OpenSearch Serverless (ADR-002)
- AWS Secrets Manager (replaces Railway env vars)
- Private networking, VPC endpoints, WAF
- OSFI E-23 model risk alignment

---

## Stretch (only after Phase 3 is solid)
- [ ] Second MCP integration
- [ ] Thin approval-gate UI (Next.js, deployed to Railway or Vercel free tier)
- [ ] Azure OpenAI swap path (config-only, shows vendor portability)

---

## ADRs to write (interview artifacts)
1. **LangGraph vs. Amazon Bedrock Agents** — why self-orchestrated; when managed wins
2. **pgvector co-located (demo) vs. dedicated vector DB (production)** — what changes,
   the cost delta, and the trigger for migrating. This is your cost-optimisation story.
3. **Bedrock Guardrails configuration** for a regulated industry
4. **Railway Hobby (demo) vs. AWS App Runner/ECS (production)** — trade-offs,
   spin-down implications, and the production trigger
5. **IAM access key (Railway) vs. IAM role (AWS compute)** — why roles aren't
   available outside AWS; least-privilege mitigation on the access key

## What NOT to do
- No AWS App Runner, ECR, ECS, VPC — not in this phase
- No OpenSearch Serverless (cost floor)
- No separate Qdrant service (pgvector covers demo needs)
- No Railway Pro upgrade unless always-on becomes a hard requirement
- No UI before the workflow works headless
- No claims of client/production deployment in the repo

## Demo script (interview — ≈3–4 min)
1. Problem: regulated orgs need agents that act, but a monolith can't be audited
2. Show the graph: LangGraph supervisor + 3 agents, Bedrock models, Guardrails active
3. Pre-warm the URL if needed, then run the golden workflow live
4. Stop at the approval gate; approve; show the PostgreSQL audit log + LangSmith trace
5. Close: "This runs on Railway Hobby for cost-efficient demo portability — total
   infrastructure cost is under CAD $35/month. In a bank this moves to AWS: ECS/App
   Runner with IAM roles, Aurora pgvector or OpenSearch, private networking, OSFI E-23
   alignment. ADR-004 maps that transition exactly." The cost story is the architect
   signal — you made a deliberate trade-off and you can articulate the production path.
