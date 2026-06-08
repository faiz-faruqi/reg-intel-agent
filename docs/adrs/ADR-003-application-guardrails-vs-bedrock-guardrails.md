# ADR-003: Application-Level Guardrails vs. AWS Bedrock Guardrails

## Status
Accepted

## Date
2026-06-07

## Context

A governed compliance system operating in a regulated industry must screen every
input and output for:
- **Denied topics** — questions about bypassing controls, hacking, or other
  off-policy content that the system should not engage with
- **PII** — Social Security Numbers, credit card numbers, email addresses, and
  other personal data that must not leak through the model's output
- **Harmful content** — offensive, dangerous, or legally sensitive text

Two implementation options were evaluated:

### Option A — AWS Bedrock Guardrails (managed)

A fully managed service that sits in the request/response path of every Bedrock
model invocation. Configured via the AWS console or API with:
- Content filters (hate, insults, sexual, violence, misconduct) with adjustable
  thresholds (None → Low → Medium → High)
- Denied topic definitions (natural language descriptions of off-limits topics)
- Sensitive information filters with built-in PII entity detection (name, SSN,
  credit card, phone, email, etc.) and a `BLOCK` or `ANONYMIZE` action
- Grounding checks — detects hallucinations by comparing the response to the
  retrieved source documents
- Word filters — block specific terms or phrases

**Pros:**
- Managed, updated by AWS — PII entity types and content classifiers improve over
  time without code changes
- Grounding check is unique — it scores the response against the retrieval context
  and blocks responses that assert facts not supported by the sources
- Native integration with Bedrock model invocations — zero additional latency
  architecture (applied in the same API call)
- Audit trail via CloudTrail and CloudWatch

**Cons:**
- Only available when calling Amazon Bedrock — tightly coupled to the model provider
- Not available in the demo tier (Railway + OpenRouter) without proxying through AWS
- Adds cost: ~$0.75–1.50 per 1,000 text units processed
- Configuration is managed in the AWS console or via SDK, not in application code —
  harder to test locally and version-control

### Option B — Application-level guardrails (custom implementation)

Guardrail logic implemented in Python in `src/guardrails.py`, applied in the
agent graph and CLI before and after model calls.

**Input guardrail (`check_input`):**
- Deny list of topic patterns matched case-insensitively against the question
- Patterns cover: `"how to hack"`, `"bypass security controls"`, `"evade compliance"`,
  `"ignore audit"`, and variations

**Output guardrail (`check_output`):**
- Regex-based PII detection: SSN (`\d{3}-\d{2}-\d{4}`), credit card
  (`\d{4}[\s-]\d{4}[\s-]\d{4}[\s-]\d{4}`), email addresses
- Returns `GuardrailResult(allowed=False, reason="<entity type>")` on match

**Pros:**
- No AWS dependency — works identically on Railway, locally, or in any environment
- Fully testable: `tests/test_guardrails.py` covers all patterns with 8 unit tests
- Zero additional cost
- Version-controlled alongside application code — guardrail changes go through
  the same PR review process as agent changes

**Cons:**
- Regex-based PII detection has false negatives — a sufficiently novel SSN format
  or an abbreviated credit card number may not match
- No grounding check — hallucination detection is enforced via citation requirement
  (`is_cited` flag) rather than semantic similarity scoring
- Deny list requires manual maintenance as new evasion patterns emerge
- No built-in severity scoring — it's binary (blocked / allowed), not tiered

## Decision

**Application-level guardrails** — Option B — for the demo tier, implemented with
a **Bedrock Guardrails-compatible API** so that the production swap is configuration-
only.

### API compatibility design

`src/guardrails.py` exposes:
```python
def check_input(text: str) -> GuardrailResult: ...
def check_output(text: str) -> GuardrailResult: ...
```

Both functions return `GuardrailResult(allowed: bool, reason: str | None)`.
The calling code in `src/cli.py` and `src/main.py` does not import from `boto3`
or any AWS SDK — it calls only this interface. In production, swapping to Bedrock
Guardrails means:
1. Create a guardrail in the AWS console and note the `guardrailId`
2. Replace the body of `check_input` and `check_output` with Bedrock
   `apply_guardrail()` SDK calls
3. The rest of the application — agents, graph, CLI, API — is unchanged

This is a one-file change with no downstream impact.

### Grounding (hallucination mitigation)

Bedrock Guardrails' grounding check is not replicated in the application layer
because it would require a second LLM call (semantic similarity scoring) that
adds latency and cost. Instead, hallucination is structurally constrained at the
prompt level:

- Every factual claim in the Analysis Agent response must carry a `[N]` citation
- `is_cited = len(citations) > 0` is checked before the response is returned
- The system prompt explicitly instructs the model: *"if a point cannot be
  supported by the documents, say so explicitly"*

This is weaker than a semantic grounding check but sufficient for demo purposes.
The production path adds Bedrock Guardrails grounding on top.

## Production path

When the service moves to AWS with Amazon Bedrock:

```python
# src/guardrails.py — production implementation
import boto3

_client = boto3.client("bedrock-runtime", region_name="ca-central-1")
_GUARDRAIL_ID = os.environ["BEDROCK_GUARDRAIL_ID"]
_GUARDRAIL_VERSION = os.environ.get("BEDROCK_GUARDRAIL_VERSION", "DRAFT")

def check_input(text: str) -> GuardrailResult:
    resp = _client.apply_guardrail(
        guardrailIdentifier=_GUARDRAIL_ID,
        guardrailVersion=_GUARDRAIL_VERSION,
        source="INPUT",
        content=[{"text": {"text": text}}],
    )
    if resp["action"] == "GUARDRAIL_INTERVENED":
        reason = resp["outputs"][0]["text"] if resp.get("outputs") else "blocked"
        return GuardrailResult(allowed=False, reason=reason)
    return GuardrailResult(allowed=True, reason=None)
```

The rest of the application is unchanged. The `check_output` function follows
the same pattern with `source="OUTPUT"`.

### Recommended Bedrock Guardrails configuration for regulated industries

| Filter | Setting | Rationale |
|--------|---------|-----------|
| Hate content | Medium | Compliance queries may include discussion of discriminatory regulations — don't over-block |
| Insults | Low | Unlikely in compliance context |
| Sexual content | High | Zero tolerance |
| Violence | Medium | Some regulatory content discusses physical security |
| Misconduct | High | Core concern — block attempts to advise on bypassing controls |
| PII — SSN, credit card, bank account | BLOCK | Never emit in compliance responses |
| PII — email, phone | ANONYMIZE | Preserve context but redact values |
| Grounding threshold | 0.75 | Flag responses where <75% of claims are grounded in retrieved context |
| Denied topics | "How to bypass compliance controls", "How to avoid regulatory reporting" | Project-specific |

## Consequences

- **Positive:** Application guardrails are fully testable locally with no AWS
  dependency. The 8-test suite runs in CI alongside the rest of the test suite.
- **Positive:** Compatible API design means production swap is a one-file change.
- **Positive:** Zero cost at demo scale.
- **Negative:** Regex PII detection has false negatives. Not suitable for production
  data handling without Bedrock Guardrails or a purpose-built PII detection service.
- **Negative:** No grounding check — hallucination mitigation relies entirely on
  the citation enforcement prompt. Weaker than semantic grounding scoring.
- **Negative:** Deny list requires manual updates. No ML-based evasion detection.

## References
- [AWS Bedrock Guardrails documentation](https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails.html)
- ADR-005 — OpenRouter (demo) vs. Amazon Bedrock (production)
