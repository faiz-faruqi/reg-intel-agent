# CLAUDE.md — Regulatory Intelligence Agent (Bedrock + Railway)

## What this project is
An open-source **reference implementation** of a governed multi-agent system for
regulated industries: it answers compliance questions and assesses regulatory
impact by retrieving grounded context and proposing actions under human approval.

Two-tier strategy:
- **Demo tier (Railway Hobby):** live public URL, ~CAD $20–35/month total.
  Used for portfolio demos and interview evidence. Services sleep after 30 min
  inactivity — pre-warm the URL before any demo (30-second wake-up).
- **Production path (AWS):** App Runner/ECS, IAM roles, private networking,
  dedicated vector DB — described in ADRs. NOT built in this phase.

> This is a reference implementation. README and docs MUST NOT claim production
> deployment at any named client. Honest framing: "production-grade reference
> implementation, deployed to a live environment, cost-optimised for demo scale."

## Architecture

### Demo tier (what we are building)
- **Orchestration:** LangGraph supervisor + specialist agents (Python)
- **API service:** FastAPI — hosted on Railway
- **Models:** Claude Sonnet / Haiku on **Amazon Bedrock** (API calls from Railway)
- **Vector store + audit log:** PostgreSQL with **pgvector** — single Railway
  PostgreSQL plugin serves both retrieval and audit. Demo-tier decision: co-located
  for simplicity and cost; production separates these concerns. See ADR-002.
- **Tracing:** LangSmith (external SaaS, API key in Railway env vars)
- **Tool access:** MCP servers (Node.js) via GitHub + Jira APIs
- **Auth to Bedrock:** IAM access key (minimal user, Bedrock invoke only) stored
  in Railway env vars. NOT an IAM role — Railway is not AWS compute. See ADR-005.
- **Public URL:** Railway auto-generated HTTPS URL (custom domain optional)

### Production path (out of scope — speak to, don't build)
AWS App Runner or ECS Fargate, IAM roles (no access keys), private networking,
dedicated vector DB (pgvector/Aurora Serverless v2 or OpenSearch), AWS Secrets
Manager. See ADRs for the transition trigger and what changes.

## Agents (3 max)
1. *Knowledge Agent* — RAG retrieval over policy + regulatory text via pgvector
2. *Analysis Agent* — drafts a compliance-grounded response, citations mandatory
3. *Action Agent* — proposes a write action via MCP tool; NEVER executes without
   human approval

## Governance requirements (non-negotiable)
1. **IAM least-privilege:** access key scoped to `bedrock:InvokeModel` and
   `bedrock:InvokeModelWithResponseStream` on target model ARNs only.
2. **Bedrock Guardrails:** content filtering, denied topics, PII handling on I/O.
3. **Human-in-the-loop:** any state-changing action requires explicit human approval.
4. **Audit log:** every agent step, tool call, decision, and approval written to
   PostgreSQL (append-only, no deletes permitted).
5. **Citations mandatory:** un-cited claims are flagged, not emitted silently.
6. **Untrusted retrieval:** validate and contain retrieved content before acting.

## Engineering conventions
- Python 3.11+, full type hints, ruff + black, pytest
- Every Bedrock and MCP call wrapped with timeout, retry, and cost ceiling
- Secrets in Railway env vars only — never in code or committed files
- Structured JSON logging; LangSmith tracing via env
- `docker compose up` runs the full stack locally (FastAPI + PostgreSQL with pgvector)
- Terraform manages AWS resources only (budget alert + IAM user for Bedrock)

## Cost guardrails
- Railway Hobby tier (not Pro) — $0 base; pay compute only
- pgvector on Railway PostgreSQL — eliminates a separate vector DB service
- Claude Haiku for routine steps; Sonnet for reasoning only
- Bedrock tokens (light demo usage): ~$7–20/month
- AWS Budget alert at $30/month tracks Bedrock token spend only
- Tag all AWS resources `project=reg-intel-agent`
- Pre-warm the Railway URL before any demo; don't pay for always-on

## Scope discipline
- 3 agents max; ONE golden workflow before any breadth
- ONE MCP integration to start; second is stretch only
- CLI approval prompt is fine for demo; web UI is stretch only
- Do NOT build AWS infra beyond IAM user + budget alert in this phase
- Before adding anything not in BUILD_PLAN.md — stop and flag it

## Definition of done
A phase is complete when its slice runs end-to-end, is traced in LangSmith,
has at least one passing test, and is demoable at the live Railway URL.

## Reference
Full phased task list: @BUILD_PLAN.md
