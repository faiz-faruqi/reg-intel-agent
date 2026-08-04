# Regulatory Intelligence Agent

> A governed, multi-agent system that answers compliance questions by retrieving
> grounded regulatory context, drafting cited responses, and proposing audited
> write actions — all under mandatory human oversight.

[![Live Demo](https://img.shields.io/badge/demo-live-brightgreen)](https://reg-intel.demo.cloudkraft.com)
[![Python](https://img.shields.io/badge/python-3.11+-blue)](pyproject.toml)
[![License](https://img.shields.io/badge/license-MIT-lightgrey)](LICENSE)

**Honest framing:** This is a production-grade reference implementation deployed
to a live environment, cost-optimised for demo scale (~CAD $20–35/month total).
It is not deployed at a named client.

---

## Live Demo

**[reg-intel.demo.cloudkraft.com](https://reg-intel.demo.cloudkraft.com)**

> **Pre-warm note:** Railway Hobby services sleep after 30 minutes of inactivity.
> If the first request is slow (10–30 s), that is a cold start. Open the URL once,
> wait ~30 seconds, then run the demo.

API endpoints:

| Method | Path | Description |
|--------|------|-------------|
| `GET`  | `/`  | Demo UI — architecture walkthrough + live query form |
| `POST` | `/query` | Run a compliance question through the agent graph |
| `GET`  | `/health` | Health check |
| `GET`  | `/docs` | Swagger / OpenAPI |

---

## What It Does

A compliance question arrives. Three specialist agents handle it in sequence,
supervised by a LangGraph state machine:

```
Question
    │
    ▼
┌─────────────────┐
│  Input Guardrail │  Denied topics · PII patterns · harmful content
└────────┬────────┘
         │
    ┌────▼────────────────────────────────────────────────────┐
    │                  LangGraph Supervisor                    │
    └────┬─────────────────┬───────────────────┬─────────────┘
         │                 │                   │
    ┌────▼────┐      ┌─────▼──────┐     ┌──────▼──────┐
    │Knowledge│      │  Analysis  │     │   Action    │
    │  Agent  │─────▶│   Agent    │────▶│   Agent     │
    └─────────┘      └────────────┘     └──────┬──────┘
    pgvector RAG     cited response      JSON proposal
    HNSW cosine      mandatory cites     {title,body,labels}
    similarity       is_cited check           │
                                         ┌────▼────────────┐
                                         │  Human Gate      │  CLI approve/reject
                                         └────┬────────────┘
                                              │ approved
                                         ┌────▼────────────┐
                                         │  GitHub Issue    │
                                         └─────────────────┘
    │
    ▼
┌──────────────────────┐
│  Output Guardrail     │  PII · harmful content on response
└──────────────────────┘
    │
    ▼
┌──────────────────────┐
│  Audit Log (Neon PG) │  Every step · append-only · DB trigger enforced
└──────────────────────┘
    │
    ▼
LangSmith Trace
```

The API (`GET /`, `POST /query`) runs the read-only path: Knowledge + Analysis agents.
The CLI (`python -m src.cli`) runs the full path including Action Agent and the human approval gate.

---

## Governance

| Pillar | Implementation |
|--------|---------------|
| **Input/output guardrails** | Application-level screens for denied topics and PII. API-compatible with AWS Bedrock Guardrails — production swap is config-only. |
| **Citations mandatory** | Every factual claim must carry a `[N]` reference. `is_cited=False` flags the response before emission. |
| **Human-in-the-loop** | `interrupt_before=["human_gate"]` pauses the LangGraph graph. No write executes without an explicit `approve` at the CLI prompt. |
| **Append-only audit log** | `BEFORE DELETE` and `BEFORE UPDATE` triggers on the `audit_log` table raise an exception — immutability enforced at the database level, not by convention. |
| **IAM least-privilege** | Bedrock IAM user scoped to `bedrock:InvokeModel` on target model ARNs only. Production moves to an IAM role — no long-lived access keys. |
| **Full observability** | Every agent step and LLM call traced in LangSmith. Replayable and attributable. |

---

## Architecture Decisions

| ADR | Decision |
|-----|----------|
| [ADR-001](docs/adrs/ADR-001-langgraph-vs-bedrock-agents.md) | LangGraph vs. Amazon Bedrock Agents |
| [ADR-002](docs/adrs/ADR-002-pgvector-collocated-vs-dedicated-vector-db.md) | pgvector co-located on Neon (demo) vs. dedicated vector DB (production) |
| [ADR-003](docs/adrs/ADR-003-application-guardrails-vs-bedrock-guardrails.md) | Application guardrails vs. AWS Bedrock Guardrails |
| [ADR-004](docs/adrs/ADR-004-railway-hobby-vs-aws-app-runner.md) | Railway Hobby (demo) vs. AWS App Runner/ECS (production) |
| [ADR-005](docs/adrs/ADR-005-openrouter-demo-vs-bedrock-production.md) | OpenRouter (demo) vs. Amazon Bedrock (production) |
| [ADR-006](docs/adrs/ADR-006-azure-openai-as-alternate-provider.md) | Azure OpenAI as an alternate demo-tier provider (config-only, validated end-to-end) |

---

## Quick Start (Local)

### Prerequisites

- Docker + Docker Compose
- Python 3.11+
- An [OpenRouter](https://openrouter.ai) API key (used for both generation and embeddings)
- Optional: [LangSmith](https://smith.langchain.com) API key for tracing

### 1. Clone and configure

```bash
git clone https://github.com/faiz-faruqi/reg-intel-agent.git
cd reg-intel-agent
cp .env.example .env
# Fill in OPENROUTER_API_KEY and DATABASE_URL in .env
```

### 2. Start the stack

```bash
docker compose up
```

This starts:
- **FastAPI** on `http://localhost:8001` (demo UI at `/`, Swagger at `/docs`)
- **PostgreSQL + pgvector** on `localhost:5432`

### 3. Initialise the database

On first run, apply the schema and seed regulatory documents:

```bash
# Apply schema (creates documents table with HNSW index + append-only audit_log)
psql $DATABASE_URL -f init-db.sql

# Seed regulatory documents into pgvector
python -m src.ingest
```

### 4. Run a query

Via the UI: open `http://localhost:8001` in your browser.

Via the API:

```bash
curl -s -X POST http://localhost:8001/query \
  -H "Content-Type: application/json" \
  -d '{"question": "What are GDPR data minimisation requirements?", "top_k": 5}' \
  | python3 -m json.tool
```

### 5. Full workflow with human approval gate (CLI)

```bash
python -m src.cli "What are GDPR data minimisation requirements?"
# → retrieves context, drafts cited response, proposes GitHub issue
# → pauses: Approve action? (approve/reject):
# → on approve: creates GitHub issue, writes audit log entry
```

Requires `GITHUB_TOKEN` and `GITHUB_REPO` set in `.env`.

---

## Environment Variables

See [`.env.example`](.env.example) for the full list. Required variables:

| Variable | Description |
|----------|-------------|
| `OPENROUTER_API_KEY` | API key for generation + embeddings via OpenRouter |
| `DATABASE_URL` | PostgreSQL connection string (with `?sslmode=require` for Neon) |
| `LANGSMITH_API_KEY` | LangSmith tracing (optional but recommended) |
| `GITHUB_TOKEN` | GitHub PAT for Action Agent issue creation (Phase 2 / CLI only) |
| `GITHUB_REPO` | Target repo in `owner/name` format |

`MODEL_PROVIDER` defaults to `openrouter`. Set it to `azure_openai` to run
against your own Azure OpenAI resource instead — see the `AZURE_OPENAI_*`
variables in `.env.example` and [ADR-006](docs/adrs/ADR-006-azure-openai-as-alternate-provider.md)
for the config-only swap, validated end-to-end.

---

## Tests

```bash
pip install -e ".[dev]"
pytest
```

Current test coverage:
- `tests/test_guardrails.py` — input and output guardrail behaviour
- `tests/test_action_agent.py` — JSON extraction, markdown fence handling, audit log write

---

## Seeded Regulatory Documents

| Document | Coverage |
|----------|----------|
| GDPR Articles 5, 13, 17 | Data processing principles, transparency, erasure rights |
| ISO/IEC 27001:2022 Annex A.8 | Technological controls |

Documents are chunked and embedded at ingest time. Add new documents to
`data/seed_documents.json` and re-run `python -m src.ingest`.

---

## Cost

| Component | Cost |
|-----------|------|
| Railway Hobby (FastAPI) | $0 base, compute-only billing (~$5–10/month with usage) |
| Neon free tier (pgvector) | $0 |
| OpenRouter (Claude Sonnet) | ~$7–20/month at light demo usage |
| AWS Bedrock IAM + Budget Alert | ~$0 (Terraform-managed, no active Bedrock calls in demo tier) |
| **Total** | **~CAD $20–35/month** |

Railway Hobby services sleep after 30 minutes of inactivity — you only pay for
active compute. Pre-warm the URL before any demo.

---

## Production Path

Moving from demo to a real engagement changes infrastructure, not application code:

| Concern | Demo (now) | Production |
|---------|-----------|------------|
| Compute | Railway Hobby | AWS App Runner / ECS Fargate |
| Database | Neon free tier | Aurora Serverless v2 + pgvector |
| Models | OpenRouter → Claude | Amazon Bedrock (direct) |
| Auth | IAM access key | IAM role (no long-lived keys) |
| Secrets | Railway env vars | AWS Secrets Manager |
| Networking | Public Railway URL | Private VPC + WAF |
| Always-on | No (sleeps) | Yes |

See [ADR-004](docs/adrs/ADR-004.md) for the full transition map and cost delta.

---

## Repo Structure

```
reg-intel-agent/
├── src/
│   ├── agents/
│   │   ├── knowledge_agent.py   # pgvector RAG retrieval
│   │   ├── analysis_agent.py    # citation-mandatory drafting
│   │   ├── action_agent.py      # GitHub issue proposal (never executes without approval)
│   │   └── supervisor.py        # LangGraph routing logic
│   ├── tools/
│   │   └── github_tool.py       # GitHub REST API wrapper
│   ├── static/
│   │   └── index.html           # Demo UI (served from GET /)
│   ├── graph.py                 # Read-only LangGraph (API path)
│   ├── cli.py                   # Full graph with HITL gate (CLI path)
│   ├── guardrails.py            # Input/output content screening
│   ├── db.py                    # pgvector retrieval + audit log writes
│   ├── ingest.py                # Document chunking + embedding
│   ├── config.py                # Pydantic settings
│   ├── state.py                 # AgentState TypedDict
│   └── main.py                  # FastAPI app
├── tests/
├── docs/adrs/                   # Architecture Decision Records
├── terraform/                   # AWS budget alert + IAM user
├── data/seed_documents.json     # Regulatory document corpus
├── init-db.sql                  # Schema: documents (HNSW) + audit_log (append-only)
├── docker-compose.yml           # Local dev stack
├── Dockerfile
└── railway.toml
```

---

## Evaluation & Assurance

An independent assurance layer lives in [`evaluation/`](evaluation/). It treats this Agent
as a system-under-test, scores its outputs with RAGAS (faithfulness, answer
relevancy, context precision, context recall, refusal correctness), and
generates an audit-ready Model Risk Assessment mapped to NIST AI RMF and
OSFI E-23.

See [evaluation/README.md](evaluation/README.md).

---

## License

MIT — see [LICENSE](LICENSE).
