# Enterprise AI Assurance Framework

An assurance layer that wraps a GenAI system, runs automated evaluation against
its actual outputs, and generates **audit-ready evidence** mapped to major AI
governance frameworks.

It treats a deployed LLM application as a *system-under-test*, scores its
behaviour, assesses its architectural controls, and produces a **Model Risk
Assessment report** — the artifact a model-risk committee or CRO consumes, not
just a metrics dashboard.

> **What this is:** a reference implementation that assures its own
> system-under-test (the Regulatory Intelligence Agent) and demonstrates an
> assurance *methodology*. It is not a client-deployed compliance product, and
> the golden-dataset ground truths should be reviewed by a subject-matter
> expert before results are used as formal evidence.

---

## Why it exists

Canadian FRFIs are inside the transition window for **OSFI Guideline E-23**
(Model Risk Management, effective 1 May 2027), which extends model-risk
expectations to AI/ML systems. Comparable expectations live in the **NIST AI
RMF**, **ISO/IEC 42001**, and the **EU AI Act**. Across all of them the gap is
the same: organizations can *describe* controls but struggle to produce
repeatable, output-level *evidence* that the controls hold. This framework
produces that evidence.

The engine is **sector-neutral**. Regulatory frameworks are a swappable
**mapping layer** — lead with E-23 in financial-services conversations, lead
with NIST/ISO everywhere else. Same engine, one mapping file.

## Architecture (six layers)

1. **Test Definition** — golden dataset (`data/golden_dataset.json`)
2. **Evaluation Engine** — runs the system-under-test (`src/agent_client.py`)
3. **Quality Scoring** — RAGAS metrics + refusal correctness (`src/metrics.py`)
4. **Red-Team** — *Phase 2* (prompt injection, jailbreak, PII leakage, etc.)
5. **Model Abstraction** — same suite across OpenRouter (demo) and AWS Bedrock
   (production path); model label is configurable
6. **Evidence & Reporting** — Model Risk Assessment report + control mapping
   matrix (`src/report.py`, `mappings/control_mappings.yaml`)

## Quick start (mock mode — no keys, no network)

```bash
pip install pyyaml
python run_assurance.py
# -> writes samples/model_risk_assessment_sample.md
```

Mock mode exercises the full pipeline with deterministic synthetic responses
(intentionally including a couple of weaker results so the report has a
realistic residual-risk section).

## Live mode (evaluate the real Agent)

```bash
pip install -r requirements.txt
cp .env.example .env          # then fill in URLs and API keys
python run_assurance.py --mode live --model-label "OpenRouter/Gemma-3-27B"
```

The harness depends only on this contract from the system-under-test:

```
POST {AGENT_BASE_URL}{AGENT_QUERY_PATH}
body:     {"question": "<str>"}
response: {"answer": "<str>", "contexts": ["<str>", ...]}
```

If your Agent's field names differ, adjust `_parse_live_response` in
`src/agent_client.py`.

### Bedrock comparison (Phase 2, low effort)

Point the system-under-test at a Bedrock-backed deployment and re-run with a
different `--model-label`, then diff the two reports. This makes the Bedrock
production path (ADR-005) demonstrable rather than only documented.

## What's measured

| Metric | Meaning | Control |
|---|---|---|
| Faithfulness | answer grounded in retrieved context | CTL-01 |
| Answer relevancy | answer addresses the question | CTL-02 |
| Context precision | retrieved context is relevant | CTL-03 |
| Context recall | relevant context was retrieved | CTL-04 |
| Refusal correctness | out-of-scope questions declined | CTL-05 |

Architectural controls (human-in-the-loop, audit logging, guardrails) are
assessed as observed activities (CTL-06 to CTL-08).

## Project layout

```
ai-assurance-framework/
├── run_assurance.py              # entrypoint
├── requirements.txt
├── .env.example
├── data/golden_dataset.json      # curated Q/A with ground truth + contexts
├── mappings/control_mappings.yaml# control -> NIST / E-23 (ISO, EU = Phase 2)
├── src/
│   ├── agent_client.py           # adapter to system-under-test (mock + live)
│   ├── metrics.py                # RAGAS (live) + deterministic scoring (mock)
│   └── report.py                 # Model Risk Assessment generator
├── docs/adr/ADR-006-ai-assurance-framework.md
└── samples/model_risk_assessment_sample.md
```

## Roadmap

- **v1 (this):** golden dataset, RAGAS metrics, refusal correctness, MRA report,
  NIST AI RMF + OSFI E-23 mappings, ADR-006.
- **Phase 2:** adversarial/red-team suite; AWS Bedrock comparison run; ISO/IEC
  42001 + EU AI Act mappings; static results viewer page.

---

Reference implementation by **CloudKraft Consulting**. Methodology pairs with
the AI Governance Maturity Assessment (organizational layer) and the Regulatory
Intelligence Agent (application layer) to cover governance from process to
system to evidence.
