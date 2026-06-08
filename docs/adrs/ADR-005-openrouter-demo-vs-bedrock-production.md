# ADR-005: OpenRouter (Demo) vs. Amazon Bedrock (Production)

## Status
Accepted

## Date
2026-06-07

## Context

The system requires two model capabilities:
1. **Text generation** — the Analysis Agent and Action Agent call an LLM to draft
   compliance responses and JSON proposals
2. **Text embeddings** — the ingest pipeline and Knowledge Agent embed documents
   and queries for pgvector cosine similarity search

Two provider options were evaluated:

### Option A — Amazon Bedrock (direct)

Amazon Bedrock provides managed access to foundation models (Anthropic Claude,
Amazon Titan, Cohere, Meta Llama, Mistral) via a unified AWS API. Models are
invoked via `boto3` with IAM credentials. Bedrock is the intended production
model layer for regulated industries because it provides:
- Data residency guarantees (models run in the configured AWS region)
- No data used for model training (explicit contractual commitment)
- Native integration with Bedrock Guardrails, Bedrock Knowledge Bases, and
  CloudWatch logging
- OSFI, SOC 2, HIPAA, and FedRAMP alignment

**Cons for demo tier:**
- Requires AWS credentials (`AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` for
  Railway, or an IAM role for AWS compute). See the IAM discussion below.
- Not free — Claude Sonnet input/output tokens are billed per use
  (~$3–15/1M tokens depending on model). Light demo usage: ~$7–20/month.
- `boto3` API differs from the OpenAI SDK interface. The LangChain Bedrock
  integration (`langchain-aws`) requires a separate client wrapper.

### Option B — OpenRouter

OpenRouter is a unified API gateway that routes to models from multiple providers
(OpenAI, Anthropic, Google, Meta, Mistral, and others) using an **OpenAI-compatible
REST interface**. Free-tier models are available at $0/request.

**Model selected for demo:** `google/gemma-4-31b-it:free`

Tested and validated:
- Follows `[N]` citation format consistently (tested in `scripts/test_free_model.py`)
- Produces valid JSON proposals for the Action Agent (`{title, body, labels}`)
- 262K context window — more than sufficient for retrieved chunks

**Embedding model:** `openai/text-embedding-3-small` via OpenRouter (1536-dim,
negligible cost at demo query volume — fractions of a cent per month)

**Pros:**
- Free generation — $0 for `google/gemma-4-31b-it:free`
- OpenAI-compatible API — LangChain's `ChatOpenAI` and `OpenAIEmbeddings` work
  without any Bedrock-specific client code
- No AWS credentials required at all in the demo tier — no IAM user, no access
  key, no Bedrock-specific IAM policy
- Model swap is a single env var: `OPENROUTER_MODEL_ID=<model_id>`

**Cons:**
- Free models have rate limits (~20 req/min, 200 req/day per OpenRouter free tier)
  and may experience provider-side availability issues
- No data residency guarantees — traffic routes through OpenRouter's infrastructure
- Not suitable for a regulated production environment where data sovereignty is
  a compliance requirement
- Free model availability changes — models are added and removed without notice

## Decision

**OpenRouter with `google/gemma-4-31b-it:free`** for the demo tier.

The decisive factor is cost and operational simplicity. The free model eliminates
generation cost entirely — the only non-zero cost is Railway Hobby compute
(~$5–10/month). This makes the total infrastructure spend ~$5–10/month, down from
the original estimate of ~$20–35/month with Bedrock.

The OpenAI-compatible API is the key enabler: both `ChatOpenAI` and
`OpenAIEmbeddings` are pointed at OpenRouter's base URL:

```python
# Generation (src/agents/analysis_agent.py, action_agent.py)
ChatOpenAI(
    model=settings.OPENROUTER_MODEL_ID,
    api_key=settings.OPENROUTER_API_KEY,
    base_url="https://openrouter.ai/api/v1",
    temperature=0,
)

# Embeddings (src/agents/knowledge_agent.py)
OpenAIEmbeddings(
    model=settings.EMBEDDING_MODEL,
    api_key=settings.OPENROUTER_API_KEY,
    base_url="https://openrouter.ai/api/v1",
    dimensions=settings.EMBEDDING_DIMENSIONS,
)
```

No Bedrock-specific code exists in the application. Swapping to Bedrock is a
configuration change, not a code change — see the production path below.

## IAM story: why no AWS credentials in the demo tier

Because the demo tier uses OpenRouter (not Bedrock), **no AWS credentials are
needed at all** in Railway. There is no IAM user, no access key, and no
`AWS_ACCESS_KEY_ID` in the Railway environment.

This is a security improvement over the original plan. The original design
required an IAM access key (a long-lived static credential) stored in Railway
env vars because Railway is not AWS compute and cannot assume an IAM role. By
routing through OpenRouter instead, the entire AWS credential surface is
eliminated from the demo tier.

### IAM in production (when Bedrock is activated)

When the service moves to AWS App Runner with Amazon Bedrock:

1. An IAM role is attached to the App Runner task — no static credentials:
```hcl
resource "aws_iam_role" "api_task_role" {
  name = "reg-intel-agent-api-task"
  assume_role_policy = jsonencode({
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "tasks.apprunner.amazonaws.com" }
    }]
  })
}
```

2. The role is scoped to `bedrock:InvokeModel` on target model ARNs only:
```hcl
Action = [
  "bedrock:InvokeModel",
  "bedrock:InvokeModelWithResponseStream"
]
Resource = [
  "arn:aws:bedrock:ca-central-1::foundation-model/anthropic.claude-3-5-sonnet*",
  "arn:aws:bedrock:ca-central-1::foundation-model/amazon.titan-embed*"
]
```

3. `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` env vars are removed.
   The boto3 credential chain picks up the instance role automatically.

## Production swap path

Swapping from OpenRouter to Bedrock requires changes to **two files only**:

### 1. `src/config.py` — update defaults
```python
# Before (OpenRouter)
OPENROUTER_API_KEY: str
OPENROUTER_MODEL_ID: str = "google/gemma-4-31b-it:free"
EMBEDDING_MODEL: str = "text-embedding-3-small"
EMBEDDING_DIMENSIONS: int = 1536

# After (Bedrock)
AWS_REGION: str = "ca-central-1"
BEDROCK_MODEL_ID: str = "anthropic.claude-3-5-sonnet-20241022-v2:0"
BEDROCK_EMBEDDING_MODEL: str = "amazon.titan-embed-text-v2:0"
EMBEDDING_DIMENSIONS: int = 1024  # ⚠ dimension change — requires DB rebuild
```

### 2. `src/agents/analysis_agent.py` and `action_agent.py` — swap client
```python
# Before (OpenRouter via ChatOpenAI)
from langchain_openai import ChatOpenAI
model = ChatOpenAI(model=settings.OPENROUTER_MODEL_ID,
                   api_key=settings.OPENROUTER_API_KEY,
                   base_url="https://openrouter.ai/api/v1")

# After (Bedrock via ChatBedrock)
from langchain_aws import ChatBedrock
model = ChatBedrock(model_id=settings.BEDROCK_MODEL_ID,
                    region_name=settings.AWS_REGION)
```

### 3. `src/agents/knowledge_agent.py` — swap embeddings client
```python
# Before (OpenRouter via OpenAIEmbeddings)
from langchain_openai import OpenAIEmbeddings
embeddings = OpenAIEmbeddings(model="text-embedding-3-small",
                               api_key=settings.OPENROUTER_API_KEY,
                               base_url="https://openrouter.ai/api/v1")

# After (Bedrock Titan via BedrockEmbeddings)
from langchain_aws import BedrockEmbeddings
embeddings = BedrockEmbeddings(model_id="amazon.titan-embed-text-v2:0",
                                region_name=settings.AWS_REGION)
```

### ⚠ Embedding dimension change requires a DB rebuild

`text-embedding-3-small` produces 1536-dim vectors. Titan Embeddings V2 produces
1024-dim vectors. The `documents` table schema is `vector(1536)` — changing models
requires:

```sql
-- Rebuild required on model swap
DROP TABLE documents;
-- Re-apply init-db.sql with vector(1024)
-- Re-run python -m src.ingest
```

This is a one-time migration cost. Lock the embedding model before seeding
production data.

## Provider comparison

| Concern | Demo (OpenRouter) | Production (Bedrock) |
|---------|------------------|---------------------|
| Generation cost | $0 (free model) | ~$3–15/1M tokens |
| Embedding cost | ~$0.02/1M tokens | ~$0.02/1M tokens (Titan) |
| Data residency | No guarantee | AWS region-locked |
| Compliance | Not suitable for regulated data | SOC 2, HIPAA, OSFI-aligned |
| Model quality | Good (Gemma 4 31B) | Higher (Claude Sonnet) |
| Rate limits | OpenRouter free tier (~200/day) | AWS account limits (configurable) |
| AWS credentials required | No | Yes (IAM role on AWS compute) |
| Client code change | — | 2 files, ~10 lines |

## Consequences

- **Positive:** $0 generation cost at demo scale. No AWS credentials in Railway.
  Clean, zero-surface demo environment.
- **Positive:** OpenAI-compatible API means the swap to Bedrock is a ~10-line
  client change — not a rewrite. Agents, state, graph, and guardrails are
  unchanged.
- **Negative:** Free model rate limits (~200 req/day on OpenRouter free tier)
  are a ceiling. Mitigated by application-level rate limiting (ADR-003 approach,
  `slowapi` — 30/day per IP on `/query`).
- **Negative:** No data residency. Demo queries should use synthetic or public
  regulatory text — not real client data.
- **Negative:** Embedding dimension change (1536 → 1024) on Bedrock swap requires
  a full DB rebuild. Must be planned as a migration step.

## References
- ADR-003 — Application guardrails vs. Bedrock Guardrails
- ADR-004 — Railway Hobby vs. AWS App Runner/ECS
- [OpenRouter free model list](https://openrouter.ai/models?order=throughput-highest&supported_parameters=free)
- [Amazon Bedrock model IDs](https://docs.aws.amazon.com/bedrock/latest/userguide/model-ids.html)
