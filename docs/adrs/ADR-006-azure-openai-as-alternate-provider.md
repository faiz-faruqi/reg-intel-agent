# ADR-006: Azure OpenAI as an Alternate Demo-Tier Provider

## Status
Accepted

## Date
2026-08-03

## Context

ADR-005 chose OpenRouter for the demo tier's generation and embeddings, with
Amazon Bedrock documented as the production path. Neither ADR previously
validated a third option: **Azure OpenAI**, provisioned directly in a
customer's own Azure subscription rather than routed through a gateway.

This matters for engagements where a client mandates Azure as their AI
platform for their own data-governance reasons — a distinct driver from
Bedrock's data-residency argument. Unlike ADR-005's production swap path,
which was documented but never executed, this ADR is based on an actual
Azure OpenAI resource, deployed models, and a live end-to-end run of the
three-agent pipeline (`knowledge_agent` → `analysis_agent` → `action_agent`).

See [`docs/diagrams/c4-azure-openai.drawio`](../diagrams/c4-azure-openai.drawio)
(or the rendered [`.svg`](../diagrams/c4-azure-openai.drawio.svg)) for a C4
container diagram of how the Azure OpenAI integration sits alongside the
rest of the system — including both live deployments (`gpt-5-mini`,
`embed-deploy`) inside the resource.

## Implementation

`MODEL_PROVIDER=azure_openai` is now a first-class option alongside
`openrouter` (`src/config.py`). A single shared factory,
[`src/llm.py`](../../src/llm.py), branches on the provider and constructs
either `ChatOpenAI`/`OpenAIEmbeddings` (OpenRouter) or
`AzureChatOpenAI`/`AzureOpenAIEmbeddings` (Azure). All four call sites
(`knowledge_agent.py`, `analysis_agent.py`, `action_agent.py`, `ingest.py`)
were previously duplicating the OpenRouter client construction directly —
they now call the shared factory, which is also what made adding a second
provider a config-only change rather than a four-file rewrite.

```python
# src/llm.py — Azure branch
AzureChatOpenAI(
    azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
    azure_deployment=settings.AZURE_OPENAI_CHAT_DEPLOYMENT,
    api_version=settings.AZURE_OPENAI_API_VERSION,
    api_key=settings.AZURE_OPENAI_API_KEY,
    timeout=30,
    max_retries=2,
)
```

Five new settings (`AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT`,
`AZURE_OPENAI_API_VERSION`, `AZURE_OPENAI_CHAT_DEPLOYMENT`,
`AZURE_OPENAI_EMBEDDING_DEPLOYMENT`), with a `model_validator` that fails
fast at startup if `MODEL_PROVIDER=azure_openai` is selected without all
four credential/deployment fields set.

## Azure OpenAI vs. OpenRouter: the real, non-cosmetic difference

OpenRouter routes on a bare model string (`OPENROUTER_MODEL_ID`) against a
single shared `base_url`. Azure OpenAI routes on a **deployment name**
(`azure_deployment`) that you create yourself inside your own resource —
the underlying model name is secondary metadata, not the routing key. This
means standing up a new model on Azure is a two-step action (deploy the
model into the resource, *then* point the app at the deployment name),
versus OpenRouter's one-line model-string swap. It's more operational
overhead, but it's also the mechanism that gives an enterprise customer
control over exactly which model versions are live in their own tenant.

## What the real validation run surfaced (not hypothetical)

Provisioning a real resource surfaced two genuine findings that a
paper-only ADR would have missed:

1. **Model catalog churn is the customer's problem to manage, not
   OpenRouter's.** At the time of this validation (August 2026), the
   `gpt-4.1` and `gpt-4.1-mini` deployments (version `2025-04-14`) were
   already in a `ServiceModelDeprecating` state and refused new
   deployments — despite still being listed in the catalog UI. We deployed
   `gpt-5-mini` instead. OpenRouter abstracts this churn away (it
   auto-fails-over across providers hosting a given model); on Azure, a
   customer's own subscription is responsible for tracking deprecations
   and redeploying — a real operational cost of the "your own tenant"
   model.

2. **Newer reasoning-style deployments reject `temperature` overrides.**
   `gpt-5-mini` returned `400 Unsupported value: 'temperature' does not
   support 0.0 with this model. Only the default (1) value is supported.`
   The OpenRouter-hosted model (`z-ai/glm-5.2`) accepts `temperature=0`,
   which the Analysis/Action agents rely on for deterministic,
   low-creativity compliance answers. `src/llm.py`'s Azure branch omits the
   `temperature` kwarg entirely rather than hardcoding a value, since this
   constraint is model-specific (likely applies to `o`-series and `gpt-5`
   reasoning models broadly) and not something the shared factory should
   paper over silently.

3. **Cross-provider embedding compatibility, confirmed rather than
   assumed.** The validation run queried Azure's `text-embedding-3-small`
   deployment against the *existing* `documents` table — embedded via
   OpenRouter's proxy to the same underlying OpenAI model — without
   re-seeding. Retrieval returned sensible, correctly-ranked results (top
   match similarity 0.537 on a GDPR data-minimisation query against the
   GDPR source chunk). Both paths produce 1536-dimension vectors from the
   same OpenAI model artifact, so no schema change or re-ingestion was
   required. (Re-ingesting with Azure-only embeddings was deliberately
   *not* done for this validation — the `documents` table lives in the
   same Neon database backing the live Railway demo, and truncating it
   would have broken the live site.)

4. **End-to-end pipeline output, unchanged in shape.** With
   `MODEL_PROVIDER=azure_openai`, the full `knowledge_agent` →
   `analysis_agent` → `action_agent` chain ran without any agent-level code
   change: 5 chunks retrieved, a correctly `[N]`-cited response produced
   (`is_cited=True`), and a valid `{title, body, labels}` JSON proposal
   from the Action Agent.

## Auth: Azure OpenAI vs. Bedrock's IAM story

ADR-005 documents Bedrock's production auth path as an IAM role attached to
compute (no static credentials). Azure OpenAI's equivalent is either an API
key (used here, simplest for a demo/validation run) or Microsoft Entra ID
token-based auth (`DefaultAzureCredential`, the closer analogue to an IAM
role — no long-lived secret, works with Managed Identity on Azure compute).
For a Railway-hosted demo (not Azure compute), Entra ID auth isn't a
natural fit — API key is the pragmatic choice, same trade-off OpenRouter's
API key already represents. A production deployment *on* Azure compute
(Container Apps, App Service) would use Managed Identity + Entra ID auth
instead, eliminating the static key the same way ADR-005's Bedrock IAM role
eliminates AWS access keys.

## Cost

Validation run (pipeline test above, plus iteration during setup): a
handful of chat completions on `gpt-5-mini` and embedding calls on
`text-embedding-3-small`. At this volume, cost is negligible — well under
$1 total. This is consistent with the pre-run estimate; Azure OpenAI has no
perpetual free tier the way OpenRouter's free Gemma model does, but at
demo/validation scale the pay-as-you-go cost is immaterial.

## Decision

Add `azure_openai` as a supported, validated `MODEL_PROVIDER` option for
engagements where a client requires their own Azure tenant. OpenRouter
remains the demo-tier default (ADR-005's reasoning is unchanged — $0
generation cost, no per-customer resource provisioning). Azure OpenAI is
documented and tested as a config-only alternative, not a replacement.

## Consequences

- **Positive:** The provider abstraction introduced by this work
  (`src/llm.py`) also makes the previously-hypothetical Bedrock swap
  (ADR-005) cheaper to eventually implement — one more branch in the same
  two functions, rather than editing four files again.
- **Positive:** A real, defensible claim — "validated against a live Azure
  OpenAI deployment" — rather than a documented-but-untested swap path.
- **Negative:** Azure OpenAI's deployment-name indirection and model
  catalog churn (finding #1 above) mean a customer running this on Azure
  takes on model-lifecycle management that OpenRouter otherwise absorbs.
- **Negative:** Model-specific quirks (finding #2) mean the shared factory
  can't fully hide provider differences — `src/llm.py`'s Azure branch
  intentionally omits `temperature` rather than guessing a universally-safe
  value, which callers should be aware of if they need deterministic output
  from a reasoning-style Azure deployment.

## References
- ADR-005 — OpenRouter (Demo) vs. Amazon Bedrock (Production)
- [Azure OpenAI Service documentation](https://learn.microsoft.com/azure/ai-services/openai/)
- [Azure OpenAI model deprecations](https://learn.microsoft.com/azure/ai-services/openai/concepts/model-retirements)
