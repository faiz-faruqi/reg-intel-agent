# Plan v2 — Regulatory Intelligence Agent: From Demo to Evidence-Backed Flagship

**Owner:** Faiz Faruqi (CloudKraft Consulting). **Executor:** any coding agent, following this file.
**Target system:** this repository: LangGraph, FastAPI, pgvector on Neon, OpenRouter, Railway, LangSmith, RAGAS.
Live demo: `https://reg-intel.demo.cloudkraft.com`.
**Optional extension:** Enterprise AI Gateway (`ai-gateway.cloudkraft.com`) as the LLM control plane (Phase 9).

This file is self-contained. It replaces the owner's original `PLAN.md` (not in the repo) and folds in
the review of it. Where the two differed, this file wins. Live progress, decisions and open questions are in
`docs/STATUS.md`; the as-built baseline is `docs/CURRENT_STATE.md`.

---

## 0. Why this plan exists

The goal is **not** more features. It is one system that shows senior architectural judgement with evidence:

1. **Measure it:** reproducible retrieval and answer-quality benchmarks.
2. **Model it:** a canonical regulatory model, so the agent queries resolved concepts instead of guessing
   from text chunks.
3. **Harden it:** authorization, prompt-injection and failure-handling tests.
4. **Explain it:** ADRs, diagrams and a production-gap matrix that an experienced architect could challenge.

Every number that ends up in documentation must come from a run that was executed and saved. Nothing is
claimed that was not measured.

**Infrastructure constraint (owner decision, 2026-10-15):** do not scale or replace infrastructure. Everything
runs on the existing Railway service, Neon Postgres (free tier), OpenRouter (cheap model) and GitHub Actions.
No new database, queue or hosted service without approval.

**Honest framing (from `CLAUDE.md`):** this is a production-grade reference implementation deployed to a
live demo environment. Never claim production deployment at any named client.

---

## 1. Working rules (mandatory for any agent)

### 1.1 Explain before you build
Before starting **each phase**, and before any step marked ⚠️, post this brief (about 10 lines) and **wait for
Faiz to reply "go"** or redirect:

```
PHASE X — <name>
Goal:         <one sentence>
What I found: <relevant facts from the repo that affect this phase>
Approach:     <3–5 bullets: what you will build and how>
Files:        <files/dirs you will create or change>
Risks:        <what could break; impact on the live demo>
Verify:       <how you will prove it works: tests, eval run, command>
Questions:    <only if a decision is genuinely Faiz's; otherwise "none">
```

If you discover mid-phase that the plan's assumptions don't match the repo, **stop and explain** before
improvising.

### 1.2 Guardrails
- **Branch per phase**, named in the phase table (section 4). Small, conventional commits. One PR per phase
  into `main`. **Never merge to `main` without Faiz's approval.**
- ⚠️ **Railway auto-deploys `main`.** A merge is a deploy. Never deploy to Railway or change production env
  vars without explicit approval. The live demo must keep working throughout.
- **New behaviour sits behind config flags** (e.g. `RETRIEVAL_MODE=dense|hybrid|hybrid_rerank|canonical`)
  with the current behaviour as the default, so the baseline stays runnable and a merge doesn't change the demo
  until a flag is flipped.
- **Schema changes are additive** (new tables or nullable columns) and go through numbered migrations
  (introduced in Phase 1). Never drop or rewrite the tables the live demo reads until the replacement is
  verified and Faiz approves the cutover.
- **Secrets** come from env only. Never commit keys. Add every new variable to `.env.example`.
- ⚠️ **LLM spend.** Use a cheap model for eval judging. Print an estimated cost before any eval run and ask
  before any single run expected to exceed **US$5**.
- **No fabricated regulatory text.** OSFI content comes from official OSFI sources (osfi-bsif.gc.ca) only. If
  a source can't be fetched, stop and ask Faiz to supply the file. Existing authored summaries must be labelled
  as summaries.
- **Golden answers are drafts until Faiz verifies them.** Never set `verified_by` yourself. The same applies
  to obligation, crosswalk and applicability confirmations: only Faiz sets `confirmed`.
- **Status labels** in all docs: `Implemented` · `Tested` · `Designed` · `Planned`. Never present
  Designed or Planned work as Implemented.
- **ADR numbering:** 001–006 live in `docs/adrs/`, ADR-007 in `evaluation/docs/adr/`. **Next free is ADR-008.**
  New ADRs go in `docs/adrs/`.
- **Interview notes:** at the end of each phase, append 3–5 talking points to `docs/interview-notes.md`:
  what was decided, what the numbers showed, what was surprising.
- **Status log:** at the start and end of each phase, update `docs/STATUS.md` (phase status, PR link,
  decisions made, open questions).

### 1.3 Engineering conventions (from `CLAUDE.md`)
Python 3.11+, full type hints, ruff (CI-enforced) and black, pytest. CI tests must stay mocked (no DB or API
keys in CI) except the Phase 2 eval smoke test, which uses repository secrets and a cost cap. Every phase
leaves CI green.

### 1.4 Definition of done (every phase)
The phase's "done when" is met, CI is green on its PR, new behaviour has at least one passing test,
`docs/STATUS.md` and `docs/interview-notes.md` are updated, and the PR description lists what changed, how it
was verified and its impact on the live demo.

---

## 2. Gap analysis

Full detail, with evidence, is in `docs/CURRENT_STATE.md` sections 7, 12 and 13. Summary:

### 2.1 Where the original plan disagreed with the repo
| # | Original assumption | Repo reality | Resolution |
|---|---|---|---|
| 1 | Build `eval/` from scratch | `evaluation/` has a RAGAS harness, 15-item golden set and MRA report; `scripts/eval.py` is a second harness | Extend `evaluation/` to 50 items; retire or wrap `scripts/eval.py`. One eval system only |
| 2 | Latest ADR is 005 | Two ADR-006 files collided | **Done in Phase 0:** assurance ADR renamed ADR-007; next free is 008 |
| 3 | Azure out of scope | Azure OpenAI is a validated config-only provider (ADR-006) | Use it in the Phase 8 comparison |
| 4 | E-23 needs sourcing | Corpus is 16 authored summaries; no official text; B-10 and B-13 absent | Phase 1 sources all three officially; keep existing rows until cutover |
| 5 | Plan is separate from BUILD_PLAN.md | `CLAUDE.md`: anything not in BUILD_PLAN.md must be flagged | This plan is approved scope (`CLAUDE.md` points here); BUILD_PLAN.md merge pending (STATUS) |
| 6 | Auth not mentioned | Time-limited access code + signed cookie exist | Roles for ACLs derive from the session in Phase 5 |
| 7 | CI eval in Phase 6 | CI runs ruff + 43 mocked tests | Eval smoke test moves to Phase 2 |

### 2.2 Technical gaps in the current system
- **Guardrails run only in the CLI**, not on `/query` or `/propose`.
- **The UI approval gate is not bound to the proposal:** `/execute` creates a ticket from the client body.
- **Ticket created before its audit row**, no idempotency; a retry can duplicate a ticket.
- **Audit log is append-only by trigger only:** no hash chain, so tampering is prevented in normal use but
  not detectable. No request ID, chunk IDs, model or prompt version, so decisions can't be replayed.
- **Rate limits likely keyed on Railway's proxy IP** (uvicorn without proxy headers).
- **No ACL columns or roles** on documents.
- **Retrieval is dense-only** on 16 un-chunked rows with no provenance. Any benchmark on it is meaningless.
- **Eval:** 15 items, no retrieval metrics, no latency or cost, no pinned config, no run folders; mock scores only.
- **No reproducibility:** prompts inline, no lockfile, no corpus hash, no migrations.
- **Sync graph inside async handlers** blocks the single worker.
- **Single point of failure per dependency**, with retry but no degradation path.
- **The approval gate is a button, not a policy:** no risk tiering, named approver or expiry.

### 2.3 Gaps in the original plan itself
- 50 questions with 5 per category gives 20-point swings per question. Report counts and bootstrap CIs.
- "Within judge noise" was undefined. Defined here: 3 baseline runs, tolerance ±0.05 on RAGAS means.
- Faiz's review time was not budgeted. Budgeted here (section 7).
- `pg_search` BM25 is probably unavailable on Neon; the hybrid arm is likely `tsvector`. Label it accurately.
- No rollback or "demo stays up" check, although `main` auto-deploys. Added to the rules (1.2).
- No data lifecycle for new guideline versions. Added (bitemporal corpus, change watcher).
- No cost-of-governance measurement. Added (Phase 8).

---

## 3. What makes this compelling (portfolio additions)

The pitch is **"a governed agent whose controls are tested, measured and mapped to the regulation it operates
under, with the numbers to show it."**

### 3.1 Headline and governance additions
| ID | Addition | Phase |
|---|---|---|
| B1 | **Regulatory change-impact mode** (headline): diff two guideline versions, list changed obligations, map to controls and gaps, propose tickets under HITL | 6 |
| B2 | **Tamper-evident audit log:** hash chain (`prev_hash`, `row_hash`), `verify_chain` command, mutation test | 5 |
| B3 | **Policy-as-code for actions:** risk tiers in YAML; high-risk needs a named approver and reason; proposals expire; rejections need a reason | 5 |
| B4 | **Cost-of-governance table:** eval with controls on and off; added latency, tokens, dollars | 8 |
| B5 | **Public evidence page** `/evidence`, built from committed run JSON | 10 |
| B6 | **Provider-portability result:** same golden set on OpenRouter and Azure OpenAI | 8 |
| B7 | **Trace-to-evidence in the UI:** citations with section path and corpus version, audit-trail link per request | 5 / 10 |
| B8 | **Red-team report:** injection and exfiltration pass rate, plus failures found and fixed | 5 |
| B9 | **Abstention as a headline metric:** correct refusals and false refusals | 2 |
| B10 | **Production-gap matrix** at 500 and 5,000 users, plus "what I'd do differently in a real bank" | 10 |

### 3.2 Reference-architecture additions (no new infrastructure)
These turn the canonical layer from a lookup table into a regulatory knowledge model.

**Core (not cut):**
| ID | Addition | What it does | Phase |
|---|---|---|---|
| R1 | Cross-framework crosswalk | Each canonical obligation links to equivalent requirements in NIST AI RMF, ISO/IEC 42001 and the EU AI Act. Recursive CTEs, no graph DB | 4b |
| R2 | Applicability engine | An institution profile (FRFI type, size, AI model use, third-party reliance) decides which obligations apply and how strongly. E-23 proportionality as YAML rules evaluated in SQL | 4b |
| R3 | Bitemporal corpus | Valid time (effective dates) and recorded time (ingested, superseded) on guidelines, sections and obligations | 1, 4a |
| R4 | Decision record and replay | Each answer persists prompt version, model ID, chunk IDs, corpus version, applicability result and policy decisions; `replay <request_id>` re-runs and diffs | 5 |
| R5 | Transactional outbox for tickets | `/execute` writes the approved action and its audit row in one transaction; a worker creates the ticket exactly once with an idempotency key | 5 |

**Next tier (cut-able, in this order: R7, R6):**
| ID | Addition | Phase |
|---|---|---|
| R6 | Claim-level grounding check: each claim checked against its cited section; unsupported claims flagged or removed | 3 |
| R7 | Regulatory change watcher: weekly GitHub Actions job detects new OSFI versions and records them | 6 |
| R8 | The agent as a governed model: its own E-23 model-inventory entry, model card, self-assessment validation report | 10 |
| R9 | Typed answer contract: one schema for claims, citations, effective dates, confidence, abstain reason | 2 |

**Backlog (only if time allows):** compliance posture register; semantic cache keyed by corpus version;
reviewer feedback loop into golden-set candidates; MCP server over the canonical tools; reversible PII
tokenisation before LLM calls.

**Rejected:** fine-tuning, a second vector DB, a graph database, multi-tenant SaaS features, a front-end
rewrite, infrastructure scaling.

---

## 4. Phase overview

| Phase | Name | Branch | Effort | Depends | Outcome |
|---|---|---|---|---|---|
| 0 | Discovery, baseline, reconciliation | `phase-0-discovery` | 0.5–1 d | — | `docs/CURRENT_STATE.md`, `baseline-v0` tag, ADR renumbered |
| H | *(Pending approval)* API governance hotfix | `hotfix-api-governance` | 0.5–1 d | 0 | Guardrails on API, signed proposals, proxy-aware rate limits |
| 1 | Corpus: versioned, bitemporal, structure-aware | `phase-1-corpus` | 1.5–2.5 d | 0 | E-23, B-10, B-13 with provenance; migrations; corpus report |
| 2 | Eval harness v2 + CI smoke test | `phase-2-eval` | 2.5–3.5 d | 1 | 50-item set, full metrics, run folders, answer contract |
| 3 | Retrieval and grounding experiments | `phase-3-retrieval` | 3–4 d | 2 | dense vs hybrid vs rerank, grounding arm; ADR |
| 4a | Canonical entity layer (E-23) | `phase-4a-canonical` | 4–5 d + review | 3 | Typed bitemporal model and tools; benchmark; ADR |
| 4b | Crosswalk and applicability | `phase-4b-crosswalk` | 3–4 d + review | 4a | R1, R2; ADR |
| 5 | Governance hardening | `phase-5-governance` | 4–5 d | 2 | ACLs, hash chain, R4, R5, policy HITL, red team, threat model, control matrix |
| 6 | Change-impact mode | `phase-6-change-impact` | 4–5 d | 1, 4a, 4b | B1 + R7, demoable in UI |
| 7 | Reliability and failure injection | `phase-7-reliability` | 1–2 d | 2 | Degradation paths, runbook, request IDs |
| 8 | Portability and cost-of-governance | `phase-8-portability` | 1–2 d | 2, 5 | Two comparison tables |
| 9 | *(Optional)* Gateway as control plane | `phase-9-gateway` | 2–3 d | 3, 7 | Routing via Gateway, overhead measured |
| 10 | Dossier and evidence page | `phase-10-dossier` | 3–4 d | all | Diagrams, ADRs, gap matrix, case study, `/evidence`, R8 |

**Total:** about 27.5–38 days without Phase 9 (29.5–41 with it), plus the hotfix and Faiz's review hours.
**Order:** strict through Phase 3; then 4a/4b and 5 in parallel (7 alongside either); then 6; then 8, 10.
Phase 9 only after 1–5 are done **and** Faiz approves.
**If time is short, cut in this order:** 9, the rerank arm of 3, 8, R7, R6. R1–R5 and Phase 6 are protected.

---

## 5. Phase specifications

### Phase 0 — Discovery and baseline freeze (done; see `docs/STATUS.md`)
**Goal:** understand what exists before changing anything. No functional code changes.
**Tasks:** inventory graph, nodes, routes, ingestion, chunking, embedding model, schema and indexes, HITL,
audit log, RAGAS setup, LangSmith, ADRs, tests, deployment; check Neon for pgvector version, `pg_search` and
`tsvector` (via `scripts/neon_probe.sql`, run by Faiz); record the corpus; run existing tests and eval; tag
`baseline-v0` on the live commit; resolve the ADR clash.
**Deliverable:** `docs/CURRENT_STATE.md`, including every mismatch between plan and repo.
**Done when:** Faiz has reviewed `CURRENT_STATE.md`, run the probe, and confirmed plan adjustments.

### Phase H — API governance hotfix (⚠️ needs Faiz's approval before starting)
**Goal:** make the live API apply the controls the demo claims, with minimal change.
**Tasks:**
1. Run `check_input` before and `check_output` after the graph in `/query` and `/propose`; return a clear
   refusal and write the guardrail decision to the audit log (mirror `src/cli.py`).
2. `/propose` returns the proposal plus a signed token (itsdangerous, with expiry) over its exact content;
   `/execute` accepts only that token and executes the signed content, never client-supplied text.
3. Trust Railway's forwarded-for header (uvicorn `--proxy-headers` with `FORWARDED_ALLOW_IPS` set for Railway)
   after confirming the current behaviour from logs; or key limits on the session where one exists.
4. `/execute` returns a generic error message; the detail goes to logs.
5. Tests for each: a denied-topic question is refused on the API; a tampered or expired token is rejected; an
   untampered token executes exactly the proposed content.
**Done when:** tests pass, CI green, PR approved, and Faiz deploys and smoke-tests the live demo.

### Phase 1 — Corpus seeding
**Goal:** a complete, provenance-rich corpus. Without it every later benchmark is meaningless.
**Tasks:**
1. Source the current official texts of OSFI **E-23** (Model Risk Management), **B-10** (Third-Party Risk
   Management) and **B-13** (Technology and Cyber Risk Management) from osfi-bsif.gc.ca. **Also obtain two
   official versions of at least one guideline** (E-23 draft vs 2025 final is the natural pair) for Phase 6.
   If fetching fails, stop and ask Faiz for the files.
2. Introduce numbered SQL migrations (`migrations/NNN_*.sql` plus a `schema_migrations` table and a small
   runner), and move the runtime-created tables (`session_usage`, `access_code`) into migrations.
3. New tables alongside `documents` (do not alter it until cutover): guidelines, versions, sections and chunks
   with **bitemporal columns** (`valid_from`, `valid_to`, `recorded_at`, `superseded_at`); superseded rows are
   kept, never overwritten.
4. Ingestion is **idempotent** (re-running doesn't duplicate; keyed on `chunk_hash`) and **versioned**
   (document version and effective date as stated in the source).
5. **Structure-aware chunking:** split on the guideline's own headings and numbered sections. Keep the old
   behaviour behind a flag for comparison.
6. Per-chunk metadata at minimum: `doc_id`, `doc_title`, `doc_version`, `effective_date`, `section_path`
   (e.g. `B-13 > 2 > 2.3`), `source_url`, `chunk_hash`, `acl_tags` (default `public`).
7. Existing authored summaries stay available but are labelled `kind = summary`; they are excluded from
   benchmark retrieval unless a run explicitly includes them.
8. Corpus report script: documents, sections and chunks counted, plus any sections that failed to parse.
9. A retrieval flag (`CORPUS=legacy|v2`, default `legacy`) so the live demo is unchanged until Faiz approves
   the cutover.
**Done when:** all three guidelines fully ingested, the corpus report shows no unexplained gaps, a spot-check
of 10 random chunks matches the source text exactly, and re-running ingest adds zero rows.

### Phase 2 — Golden set and evaluation harness
**Goal:** one command that produces a reproducible quality, latency and cost report.
**Golden set:** extend `evaluation/data/golden_dataset.json` (or migrate it to `evaluation/data/golden_set.jsonl`)
to **50 questions**:

| Category | Count | Example shape |
|---|---|---|
| Exact identifier | 10 | "What does section X of B-13 require for …?" |
| Conceptual | 10 | "How does OSFI expect model risk to be tiered?" |
| Cross-guideline | 10 | Needs both B-10 and E-23 (e.g. third-party models) |
| Ambiguous | 5 | Underspecified; correct behaviour is to clarify or scope |
| No answer in corpus | 10 | Correct behaviour is to **abstain** |
| Version / temporal | 5 | Sensitive to effective dates or versions |

Schema per item:
```json
{"id":"q001","question":"...","category":"exact_identifier",
 "expected_answer":"...","expected_sources":["B-13#2.3"],
 "must_abstain":false,"acl_role":"public","as_of":null,"notes":"","verified_by":null}
```
The agent drafts questions and expected answers from the Phase 1 corpus. ⚠️ **Faiz verifies** before any
reported number uses the set.

**Harness** (in `evaluation/`, run via `make eval CONFIG=<name>`):
- Retrieval: **Recall@5** and **MRR** against `expected_sources`.
- Answer quality (RAGAS): faithfulness, answer relevancy, context precision, context recall.
- Citation correctness: do the cited sections support the claim?
- **Abstention accuracy** on `must_abstain` items and the false-abstention rate on answerable ones.
- **p50/p95 latency**, time to first token if streaming exists, **tokens and estimated cost** per query and per
  correct answer.
- Pin per run: model IDs, judge model, prompt version, retrieval mode, corpus hash, git SHA, dependency lock hash.
- Output `evaluation/runs/<timestamp>_<config>/results.json` and `report.md`; `compare.py` diffs two runs.
- Prompts move to versioned files (`prompts/*.md`), not inline strings.
- Add a lockfile (e.g. `pip-compile` or `uv lock`) so runs pin their dependency set.
- **R9 typed answer contract:** one Pydantic model (claims, citations with section path and version,
  effective dates, confidence, abstain reason) used by the API response, eval and audit. Bound `top_k`.
- **Statistics:** 3 baseline runs, report mean ± range, bootstrap CIs on retrieval metrics, raw counts per
  category. Tolerance for "reproduces": ±0.05 on RAGAS means.
- **Pre-register** Phase 3 and 4 success criteria in `evaluation/PREREGISTRATION.md` before running them (for
  example "hybrid must raise exact-identifier Recall@5 by ≥0.10 without lowering conceptual by >0.03").
- **CI smoke test:** 10-item subset with a regression threshold, using repository secrets and a cost cap.
**Done when:** a baseline run on the verified set is committed and a second run with the same config
reproduces it within tolerance.

### Phase 3 — Retrieval and grounding experiments
**Goal:** an evidence-backed retrieval decision.
**Configurations:**
- **A — Baseline:** dense retrieval on Phase 1 structure-aware chunks (also run old chunking once).
- **B — Hybrid:** dense plus lexical (`pg_search` BM25 if the probe shows it, otherwise `tsvector`), fused with
  Reciprocal Rank Fusion.
- **C — Hybrid + rerank:** B followed by a cross-encoder reranker.
- ⚠️ **Reranker choice:** before building C, present local cross-encoder vs hosted rerank API (Railway memory
  and CPU, latency, cost, data leaving the boundary). Faiz decides.
- **R6 grounding arm:** claim-level support check with the cheap judge model; report the unsupported-claim
  rate with and without it, plus added latency and tokens.
**Deliverables:** `RETRIEVAL_MODE` flag for all configurations; comparison report with per-category metrics,
latency and cost deltas, and **where each configuration regressed**; ADR-008 *Dense vs hybrid vs reranked
retrieval* (context, options, measured evidence, decision, consequences, what would make you revisit it).
**Done when:** report and ADR written, chosen configuration is the default behind the flag (not deployed).

### Phase 4a — Canonical entity layer (E-23 only)
**Goal:** stop the agent inferring what a regulatory concept *is* from text similarity. Resolve concepts at
ingest; give the agent typed tools.
**Principle:** embeddings encode similarity, not meaning. Meaning is modelled above the vector store, and the
vector index points back to canonical IDs.
**Model** (relational tables in Postgres, all bitemporal):
- Entities: `guideline`, `section`, `expectation` (an OSFI principle or expectation statement), `obligation`
  (normalised, atomic requirement derived from an expectation), `control` (from the CloudKraft AI Control
  Framework), `evidence_type`.
- Relationships: section *part-of* guideline; expectation *stated-in* section; obligation *derived-from*
  expectation; obligation *cross-references* obligation (including across guidelines); obligation
  *satisfied-by* control; control *evidenced-by* evidence_type.
- `chunk_entity` links every chunk to one or more canonical IDs.
**Ingest-time resolution:** an LLM **proposes** entities and links; deterministic rules validate them (section
numbering, ID formats); each proposal has `status = proposed | confirmed | rejected`. Extraction output is
cached and versioned so evals don't re-pay. ⚠️ A small CLI or admin endpoint lets Faiz confirm proposals in
batches; only `confirmed` links are used by default.
**Typed agent tools:** `get_obligations(guideline_id, section?, as_of?)`, `get_cross_references(obligation_id)`,
`get_controls_for_obligation(obligation_id)`, `compare_versions(guideline_id, from_version, to_version)` (only
if version data supports it). Free-text retrieval stays available for explanation and nuance.
**Benchmark:** `RETRIEVAL_MODE=canonical` (typed tools plus the Phase 3 winner); rerun the eval. Exact-identifier,
cross-guideline and version categories should move most; report honestly if they don't.
**Deliverables:** migration, resolution pipeline, review CLI, typed tools, eval comparison, ADR *Canonical
regulatory model above the vector store*.
**Done when:** E-23 fully resolved and confirmed, canonical mode benchmarked against the Phase 3 winner, ADR written.

### Phase 4b — Crosswalk and applicability
**Goal:** a regulatory knowledge model across frameworks and institution types.
**Tasks:**
1. **R1 crosswalk:** link confirmed E-23 obligations to requirements in NIST AI RMF (first), then ISO/IEC 42001
   and the EU AI Act if review time allows. Each link has a relation type (`equivalent`, `partial`, `related`)
   and the same proposed/confirmed/rejected status. Only confirmed links are used.
2. **R2 applicability:** versioned YAML rules, evaluated in SQL, over 2–3 **synthetic** institution profiles
   (suggested: large domestic bank; small FRFI with limited model use; insurer relying on third-party models).
   Golden cases assert which obligations apply to each profile.
3. Typed tools: `get_crosswalk(obligation_id)`, `get_applicable_obligations(profile_id, as_of)`.
4. ADR: *Crosswalk and applicability as rules over the canonical model*.
**Done when:** crosswalk confirmed for the chosen frameworks, applicability golden cases pass, ADR written.
Docs state that the crosswalk is the author's interpretation, not an official OSFI or NIST mapping, and that
profiles are synthetic.

### Phase 5 — Governance hardening
**Goal:** demonstrate enterprise controls with automated tests, explicit about what is only designed.
**Tasks:**
1. **Document-level authorization:** enforce `acl_tags` inside the retrieval SQL (filter **before** content
   reaches the LLM, never by post-filtering the answer). Add a synthetic restricted set (e.g. "internal model
   inventory") visible only to one role; roles derive from the session.
2. **Negative authorization tests:** for each role, restricted content never appears in retrieved context,
   answers, citations, or LangSmith traces (redact or disable input capture for restricted sessions).
3. **Prompt-injection suite:** malicious documents with embedded instructions plus adversarial queries; assert
   no instruction-following, no system-prompt leak, no tool actions. Report a pass rate (B8).
4. **HITL policy (B3):** risk-tier YAML; high-risk actions need a named approver and reason; proposals expire;
   rejections need a reason. Tests prove no bypass (builds on Phase H tokens).
5. **Tamper-evident audit (B2):** hash chain, `verify_chain`, test that a mutated row is detected; document
   that the table owner can still drop triggers and what detection covers.
6. **R4 decision record + `replay <request_id>`**, with a test that replay under the same pinned config
   reproduces the stored retrieval set. Request ID shared by logs, audit rows and traces.
7. **R5 ticket outbox:** tests for double-click, worker crash and retry producing exactly one ticket.
8. **PII:** detect and redact PII in logs and traces (add Canadian SIN), or document as `Designed` if out of scope.
9. Store the access code hashed; constant-time comparison for admin key and code.
**Deliverables:** `tests/security/`, `docs/threat-model.md` (STRIDE, trust boundaries), `docs/control-matrix.md`
mapping each control to its status label, its test, the NIST AI RMF function and OSFI E-23 expectation.
**Done when:** the security suite runs in CI and the control-matrix labels are accurate.

### Phase 6 — Change-impact mode (headline feature)
**Goal:** show what a regulatory change means for obligations and controls.
**Tasks:** diff two versions of a guideline into changed, added and removed obligations; show the profiles they
apply to, affected controls and crosswalked frameworks; the Action Agent proposes tickets under HITL; demo path
in the UI. **R7 change watcher:** weekly GitHub Actions cron that detects and records a new OSFI version only;
ingesting it and opening tickets still goes through HITL.
**Eval:** about 10 golden change-impact cases with expected changed obligations; report precision and recall.
**Done when:** an end-to-end change report on real guideline versions is scored and demoable.

### Phase 7 — Reliability
**Goal:** show how the system behaves when dependencies fail.
**Tasks:** timeouts, retries with backoff and graceful degradation for LLM provider errors, Neon
unavailability and reranker failure (fall back to hybrid without rerank and say so in response metadata); run
the graph off the event loop (thread pool); failure-injection tests for 429, 5xx, slow responses and database
disconnects; health (`/health`) and readiness (checks DB) endpoints; structured logs with the request ID tied
to LangSmith traces.
**Deliverables:** `tests/resilience/`, `docs/runbook.md` (common failures, detection, recovery).
**Done when:** CI green and failure-injection results recorded in the runbook.

### Phase 8 — Portability and cost of governance
**Tasks:** run the golden set on OpenRouter and Azure OpenAI (quality, latency, cost deltas); run with controls
on and off (guardrails, grounding, audit, HITL) and report added latency, tokens and dollars.
**Done when:** two comparison tables, each linked to run folders.

### Phase 9 — *(Optional)* Gateway as LLM control plane
Only after Phases 1–5 are complete **and** Faiz approves.
**Tasks:** route LLM calls through the Gateway behind `LLM_VIA_GATEWAY=true`; extend routing to a policy based
on sensitivity (restricted ACL goes local-only), complexity and budget; per-request telemetry (model, tokens,
cost, latency, cache hit, fallback reason); rerun the eval with and without the Gateway.
**Deliverables:** integration ADR, routing policy backed by measurements.

### Phase 10 — Architecture dossier and evidence page
**Deliverables** (`docs/`):
1. Mermaid diagrams: C4 context, C4 container, query sequence (with the HITL path), trust boundaries.
2. ADR set at minimum: chunking strategy, retrieval mode, reranker, canonical model above the vector store,
   crosswalk and applicability, pgvector vs a dedicated vector DB (update ADR-002), authorization at retrieval,
   provider and Bedrock swap path (update ADR-005), Gateway routing if Phase 9 was done.
3. `docs/production-gap-matrix.md`: each capability with status label, what a 500- and 5,000-user enterprise
   rollout needs, estimated effort.
4. `docs/case-study.md` for faizfaruqi.com: executive summary, requirements and quality attributes,
   architecture views, key decisions, evaluation results (method and limitations), security assessment,
   operational model, production gaps. Only measured numbers, each linked to its run folder.
5. `/evidence` page built from committed run JSON, not hand-typed numbers.
6. **R8:** the agent's own E-23 model-inventory entry and model card, generated from run data and labelled a
   self-assessment, not an independent validation.
7. README leads with the benchmark summary and links to the evidence.
**Done when:** Faiz has reviewed the dossier and every number traces to a committed eval run.

---

## 6. Out of scope for the coding agent
- Website and LinkedIn copy (Faiz handles these).
- A full Azure port of the agent (the config-only provider path already exists).
- Production deployment and infrastructure scaling. Faiz approves and triggers each deploy.

## 7. Review budget (Faiz)
About 2 h golden-set verification (Phase 2), 4–6 h obligation confirmation (4a), 2–3 h crosswalk confirmation
(4b), plus PR reviews and deploy smoke tests.

## 8. Risks
1. Phase 4a/4b review burden and extraction quality → E-23 only, NIST first, accept and report lower coverage.
2. Corpus cutover breaks the live demo → new tables, `CORPUS` flag default `legacy`, keep old rows until verified.
3. Cheap-model variance inflates judge noise → fixed judge model, 3 runs, stated tolerance.
4. Neon free-tier storage/compute → measured by the Phase 0 probe; size entity tables accordingly.
5. Scope creep → B1–B3 and R1–R5 core; B4–B9 and R6–R9 cut-able; backlog only if time allows.
6. Crosswalk read as authoritative → relation type and confirmation status shown; stated as the author's interpretation.
7. Applicability read as compliance advice → profiles labelled synthetic; output stated not to be regulatory advice.
8. A merge silently changes the demo → flags default to current behaviour; additive migrations; Faiz deploys.

Open decisions and their current answers live in `docs/STATUS.md`.
