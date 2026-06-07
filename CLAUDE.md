# CLAUDE.md — Regulatory Intelligence Agent

## What this project is
An open-source **reference implementation** of a governed multi-agent system for
regulated industries: it answers compliance questions and assesses regulatory
impact by retrieving grounded context and proposing actions under human approval.

Two-tier strategy:
- **Demo tier (Railway Hobby):** live at `https://reg-intel.demo.cloudkraft.com`,
  ~CAD $5–10/month compute + negligible embeddings (free generation model).
  Services sleep after 30 min inactivity — pre-warm before any demo (30s wake-up).
- **Production path (AWS):** App Runner/ECS, IAM roles, private networking,
  dedicated vector DB — described in ADRs. NOT built in this phase.

> This is a reference implementation. README and docs MUST NOT claim production
> deployment at any named client. Honest framing: "production-grade reference
> implementation, deployed to a live environment, cost-optimised for demo scale."

## Architecture (as built)

### Demo tier — what is running now
- **Orchestration:** LangGraph supervisor + 3 specialist agents (Python)
- **API service:** FastAPI — hosted on Railway Hobby, auto-deploys from `main`
- **Models:** `google/gemma-4-31b-it:free` via **OpenRouter** for generation;
  `text-embedding-3-small` via OpenRouter for embeddings (1536-dim)
- **Vector store:** Neon free tier PostgreSQL with **pgvector** (HNSW index)
- **Audit log:** Same Neon DB, `audit_log` table — append-only enforced by
  `BEFORE DELETE` and `BEFORE UPDATE` triggers
- **Tracing:** LangSmith (external SaaS, API key in Railway env vars)
- **GitHub tool:** `src/tools/github_tool.py` — GitHub REST API via `requests`;
  creates issues after human approval (CLI only)
- **Rate limiting:** `slowapi` — `/query` 10/min 30/day, `/propose` 5/min 15/day per IP
- **Demo UI:** `src/static/index.html` served from `GET /` — explains architecture,
  governance pillars, and includes a live query form + propose-action demo
- **Custom domain:** `reg-intel.demo.cloudkraft.com` → Railway via Bluehost DNS CNAME

### API paths
- `GET /` — Demo UI (HTML)
- `POST /query` — Knowledge + Analysis agents (read-only, rate limited)
- `POST /propose` — All 3 agents, returns proposal without executing (rate limited)
- `GET /health` — Health check
- `GET /docs` — Swagger UI

### CLI path (full governance workflow)
```
python -m src.cli "question"
```
Runs Knowledge → Analysis → Action agents, pauses at HITL gate
(`interrupt_before=["human_gate"]`), prompts approve/reject, then executes
or logs rejection. Requires `GITHUB_TOKEN` and `GITHUB_REPO` env vars.

### Production path (out of scope — speak to, don't build)
AWS App Runner or ECS Fargate, IAM roles (no access keys), private networking,
Aurora Serverless v2 + pgvector or OpenSearch, AWS Secrets Manager.
See ADRs for the transition trigger and what changes.

## Agents (3)
1. **Knowledge Agent** — embeds question, retrieves top-k chunks via pgvector HNSW
2. **Analysis Agent** — drafts cited response; `is_cited=False` flags un-cited output
3. **Action Agent** — proposes GitHub issue as JSON `{title, body, labels}`;
   NEVER executes without explicit human approval

## Governance requirements (non-negotiable)
1. **Guardrails:** application-level input/output screening for denied topics and PII;
   API-compatible with AWS Bedrock Guardrails (production swap is config-only)
2. **Human-in-the-loop:** any state-changing action requires explicit human approval
3. **Audit log:** every agent step, tool call, decision, and approval written to
   PostgreSQL (append-only, no deletes or updates permitted — DB trigger enforced)
4. **Citations mandatory:** un-cited claims flagged, not emitted silently
5. **Rate limiting:** per-IP limits prevent API key abuse and runaway costs

## Engineering conventions
- Python 3.11+, full type hints, ruff + black, pytest
- Secrets in Railway env vars only — never in code or committed files
- `docker compose up` runs the full stack locally (FastAPI + PostgreSQL with pgvector)
- Terraform manages AWS resources only (budget alert + IAM user stubs — not active)

## Cost (current)
- Railway Hobby (FastAPI compute): ~$5–10/month
- Neon free tier (pgvector + audit log): $0
- OpenRouter `google/gemma-4-31b-it:free` generation: $0
- OpenRouter `text-embedding-3-small` embeddings: ~$0.00 at demo query volume
- **Total: effectively ~$5–10/month**

## Security constraints (must remain in effect)
- Never hardcode secrets — all credentials via env vars only
- Do not use OPENAI_API_KEY. Use OPENROUTER_API_KEY for both generation and
  embeddings. Wire both clients to `https://openrouter.ai/api/v1`
- Before adding anything not in BUILD_PLAN.md — stop and flag it

## Scope discipline
- 3 agents max — done
- ONE MCP/tool integration (GitHub REST) — done; second is stretch only
- Web UI delivered (was stretch — now done)
- Do NOT build AWS infra beyond IAM user + budget alert in this phase
- ADRs are the next priority after CI

## Definition of done
A phase is complete when its slice runs end-to-end, is traced in LangSmith,
has at least one passing test, and is demoable at the live Railway URL.

## Reference
Full phased task list: @BUILD_PLAN.md
