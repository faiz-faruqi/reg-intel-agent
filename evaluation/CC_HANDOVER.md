# Claude Code Handover — Enterprise AI Assurance Framework

## What this is
An assurance/evaluation layer for the Regulatory Intelligence Agent. It treats
the live Agent as a system-under-test, scores its outputs with RAGAS, and
generates an audit-ready Model Risk Assessment (MRA) report mapped to NIST AI
RMF and OSFI E-23.

It lives as an isolated `evaluation/` directory inside the existing
`reg-intel-agent` repo. **Do not touch any existing Agent code.**

---

## Target repo
`https://github.com/faiz-faruqi/reg-intel-agent`

---

## Step 1 — Place files

Unzip `ai-assurance-framework.zip`. Rename the root folder from
`ai-assurance-framework` to `evaluation` and place it inside the repo root.

Final structure inside the repo:

```
reg-intel-agent/
├── app/                          ← existing Agent code, DO NOT TOUCH
├── evaluation/                   ← everything from the zip goes here
│   ├── CC_HANDOVER.md            ← this file
│   ├── run_assurance.py
│   ├── requirements.txt
│   ├── .env.example
│   ├── data/
│   │   └── golden_dataset.json
│   ├── mappings/
│   │   └── control_mappings.yaml
│   ├── src/
│   │   ├── agent_client.py
│   │   ├── metrics.py
│   │   └── report.py
│   ├── samples/                  ← created at runtime
│   └── docs/adr/
│       └── ADR-006-ai-assurance-framework.md
└── README.md                     ← update per Step 4
```

---

## Step 2 — Verify mock mode runs clean

Mock mode needs no API keys and no running Agent. Run it first to confirm
the full pipeline works before touching the live system.

```bash
cd evaluation/
pip install pyyaml
python run_assurance.py
```

Expected output:
```
[assurance] mode=mock  items=15  model=mock-model
[assurance] aggregate scores:
            faithfulness           0.86
            answer_relevancy       0.906
            ...
            refusal_correctness    1.0
[assurance] report written to samples/model_risk_assessment_sample.md
```

Open `samples/model_risk_assessment_sample.md` and confirm it contains a
full Model Risk Assessment report with a control mapping table.

---

## Step 3 — Fix the knowledge base (Agent side)

**This must be done before live mode.** The Agent currently has the 2017
version of OSFI E-23 ingested. The golden dataset questions target the 2025
final version (effective May 1, 2027).

3a. Remove 2017 E-23 chunks from pgvector (Neon). Identify them by metadata
    date or source string containing "August 2017" or "2017".

3b. Ingest the 2025 final guideline from:
    `https://www.osfi-bsif.gc.ca/en/guidance/guidance-library/guideline-e-23-model-risk-management-2027`
    Use the existing ingestion pipeline.

3c. Verify with:
```bash
curl -X POST https://reg-intel.demo.cloudkraft.com/query \
  -H "Content-Type: application/json" \
  -d '{"question": "When does OSFI E-23 take effect?"}'
```

Expected: response references **May 2027** and the **18-month transition
period**. Citations should be non-empty and reference the 2025 document.

Do not proceed to Step 4 until this curl returns the correct answer.

---

## Step 4 — Configure environment for live mode

```bash
cd evaluation/
cp .env.example .env
```

Fill in `.env`:

```
AGENT_BASE_URL=https://reg-intel.demo.cloudkraft.com
AGENT_QUERY_PATH=/query
AGENT_MODEL_LABEL=OpenRouter/Gemma-3-27B
OPENROUTER_API_KEY=<your OpenRouter key>
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
JUDGE_MODEL=openai/gpt-4o-mini
OPENAI_API_KEY=<your OpenAI key>
EMBED_MODEL=text-embedding-3-small
```

---

## Step 5 — Run live mode

```bash
cd evaluation/
pip install -r requirements.txt
python run_assurance.py --mode live --model-label "OpenRouter/Gemma-3-27B"
```

This calls the live Agent for all 15 golden dataset questions, scores
responses with RAGAS, and writes the MRA report to
`samples/model_risk_assessment_sample.md`.

---

## Step 6 — Update root README.md

Add this section to the repo root `README.md`:

```markdown
## Evaluation & Assurance

An independent assurance layer lives in `evaluation/`. It treats this Agent
as a system-under-test, scores its outputs with RAGAS (faithfulness, answer
relevancy, context precision, context recall, refusal correctness), and
generates an audit-ready Model Risk Assessment mapped to NIST AI RMF and
OSFI E-23.

See [evaluation/README.md](evaluation/README.md).
```

---

## Live Agent response shape (already handled in agent_client.py)

The Agent returns:
```json
{
  "question": "...",
  "response": "...",
  "citations": ["[2] OSFI E-23 — full citation string", "..."],
  "is_cited": true
}
```

`agent_client.py` already maps `response` → `answer` and `citations` →
`contexts`. No further changes needed unless the Agent's API shape changes.

---

## What NOT to do
- Do not touch `app/`, `docker-compose.yml`, or any existing Agent files
- Do not add evaluation dependencies to the Agent's existing `requirements.txt`
- Do not deploy the evaluation suite as a service — it runs as a local CLI tool
- Do not commit `.env` to the repo — it is already in `.gitignore` (add it if not)

---

## Success criteria
1. `python run_assurance.py` (mock) runs clean and generates the MRA report
2. Curl test returns May 2027 answer with non-empty citations
3. `python run_assurance.py --mode live` runs and generates a real MRA report
4. Root README references the evaluation directory
5. No existing Agent files modified
