# Demo Script — Regulatory Intelligence Agent
### Interview walkthrough · ~3–4 minutes

---

## Before you start

- Open `https://reg-intel.demo.cloudkraft.com` in a browser tab — **pre-warm it** (Railway
  Hobby sleeps after 30 min of inactivity; open the page once, wait 30 s, then demo).
- Have a second tab open to your Jira board (`KAN` project) so you can show the ticket
  after approving.
- Know your one-line summary: *"A governed multi-agent system that answers compliance
  questions, proposes write actions, and enforces human approval before anything executes."*

---

## 1 · Problem statement `[30 s]`

> *"Regulated organisations — banks, insurers, fintechs — are under pressure to use AI
> for compliance work. But a monolithic LLM you can't audit isn't acceptable to OSFI,
> GDPR regulators, or an internal risk committee.*
>
> *The question I set out to answer was: can you build an agent system that is genuinely
> useful AND auditable, with a hard human gate on anything that changes state? This is
> that system."*

---

## 2 · Architecture walkthrough `[45 s]`

**[Point to the pipeline diagram on the page]**

> *"Three specialist agents in a LangGraph supervisor loop."*

Walk down the pipeline visually:

- **Knowledge Agent** — embeds the question, runs cosine similarity search over regulatory
  docs in pgvector (Neon, HNSW index). Right now we have GDPR, ISO 27001, Basel III,
  OSFI E-23, OSFI B-20, and PIPEDA seeded.
- **Analysis Agent** — drafts a cited response. Every factual claim requires an inline
  `[N]` citation — un-cited output is flagged, not silently emitted.
- **Action Agent** — proposes a Jira ticket as `{title, body, labels}` JSON. It never
  executes anything on its own.
- **HITL gate** — the graph pauses. A human must approve or reject. The decision is
  written to the audit log either way.

> *"The governance layer runs across all of this: input/output guardrails, append-only
> audit log in PostgreSQL (DELETE and UPDATE are blocked by a database trigger), and
> citation enforcement. All five architectural decisions are documented in ADRs."*

---

## 3 · Live query `[45 s]`

**[Click the example query or type it]:**
> `What does OSFI E-23 require for model validation?`

**[Click "Run Query →"]**

While it loads (5–15 s), narrate:

> *"The Knowledge Agent is embedding the question and searching the vector store.
> The Analysis Agent is calling the free Gemma 4 31B model via OpenRouter —
> zero generation cost at demo scale."*

**[When response appears — point to the citations]:**

> *"Every claim has a source. If the model tries to assert something not grounded in
> the retrieved documents, the citation flag fires and we know the response is unreliable.
> That's structural hallucination mitigation — not a prompt prayer."*

---

## 4 · Full pipeline + HITL `[60 s]`

**[Click "Run Full Pipeline + Propose Action →" with the same question]**

While it loads, narrate:

> *"This runs all three agents. The Action Agent is proposing a Jira ticket to track
> the model validation gap it just identified."*

**[When proposal appears — point to the title, body, and labels]:**

> *"The ticket is proposed, not created. The graph is paused at the HITL gate."*

**[Click "Approve & Create Ticket"]:**

> *"I approve. The `/execute` endpoint calls the Jira API, creates the ticket,
> and writes the approval decision to the audit log."*

**[Switch to Jira tab — show the ticket in the KAN board]:**

> *"There it is — `KAN-[N]`. The full chain: question → retrieval → analysis →
> proposal → human decision → write. Every step is in the audit log."*

---

## 5 · Governance pillars `[30 s]`

> *"Three things make this production-grade rather than a demo toy:"*

1. **Audit log** — every agent step, tool call, and approval is appended to PostgreSQL.
   The table has a `BEFORE DELETE` and `BEFORE UPDATE` trigger that raises an exception —
   tamper-proof by design, not by policy.

2. **Guardrails** — input and output are screened before and after the model. The API
   mirrors the AWS Bedrock Guardrails interface, so swapping to managed guardrails in
   production is a one-file change.

3. **Citations mandatory** — the system prompt forbids un-cited claims. The `is_cited`
   flag is checked on every response. Un-cited output is surfaced to the caller, not
   swallowed.

---

## 6 · Production path `[30 s]`

> *"This runs on Railway Hobby and Neon free tier — about CAD $5–10/month compute,
> zero generation cost because Gemma 4 31B is free on OpenRouter. That's intentional:
> I wanted a live, demoable system, not a slide deck.*
>
> *In a regulated institution this moves to AWS: App Runner or ECS Fargate with an
> IAM role, Amazon Bedrock direct for Claude Sonnet, Aurora Serverless v2 with pgvector
> or OpenSearch, private networking, AWS Secrets Manager. The model swap is about ten
> lines — the agents, graph, and governance layer don't change. ADR-004 and ADR-005
> map the transition trigger and migration steps exactly."*

---

## 7 · Close `[15 s]`

> *"It's open source, live at `reg-intel.demo.cloudkraft.com`, CI green, eval harness
> scoring 10 fixed compliance questions for faithfulness. Happy to walk through any of
> the five ADRs or dig into the LangGraph graph design."*

---

## Common follow-up questions

**"Why LangGraph and not Amazon Bedrock Agents?"**
> LangGraph's `interrupt_before` primitive is a first-class HITL gate — the graph
> checkpoints state and waits for `update_state()`. Bedrock Agents would need a custom
> Lambda approval flow to replicate this. When everything is already in AWS and you want
> zero orchestration ops, Bedrock Agents wins. ADR-001 has the full comparison.

**"Why not just use RAG with a single LLM call?"**
> Separation of concerns. The Knowledge Agent owns retrieval and can be swapped
> (pgvector today, OpenSearch tomorrow) without touching generation. The Analysis Agent
> enforces citation. The Action Agent is isolated so its proposals can never execute
> without going through the gate. A monolith would collapse those boundaries.

**"How do you handle hallucinations?"**
> Two layers. Structurally: every factual claim must carry a `[N]` citation — the
> prompt forbids un-cited assertions and the `is_cited` flag exposes violations.
> In production: Bedrock Guardrails adds a grounding check that scores each claim
> against the retrieved source documents and blocks responses below a 75% grounding
> threshold. ADR-003 covers the swap path.

**"What's the OSFI E-23 angle?"**
> OSFI E-23 governs model risk at federally regulated financial institutions — it
> requires a model inventory, independent validation, and ongoing monitoring. An
> AI system used for compliance decisions *is itself a model* under E-23. The audit
> log, citation enforcement, and HITL gate are direct mitigations for the E-23
> requirements around use tests, human oversight, and model governance. The production
> path adds the formal model risk framework on top.

**"Could this scale to production query volumes?"**
> Railway Hobby sleeps — that's a demo trade-off I made deliberately. On AWS App
> Runner with Aurora pgvector you get always-on, autoscaling, and the HNSW index
> handles tens of thousands of documents without a performance cliff. The rate
> limiting (10/min per IP today) would be replaced with API key management and
> per-tenant quotas.
