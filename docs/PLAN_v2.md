# Plan v2 — Regulatory Intelligence Agent: Evidence-Backed Flagship

Supersedes the uploaded PLAN.md. Same working rules (explain-then-"go" per phase, branch per phase,
no Railway deploy/env change without approval, status labels `Implemented|Tested|Designed|Planned`,
no fabricated regulatory text, Faiz verifies golden answers, every published number traces to a saved run).

## A. Gap analysis

### A1. Where PLAN.md disagrees with the repo (fix before starting)
| # | PLAN.md assumes | Repo reality | Resolution |
|---|---|---|---|
| 1 | Build `eval/` from scratch | `evaluation/` already has RAGAS harness, 15-item golden set, MRA report, NIST/E-23 mapping; `scripts/eval.py` is a second, simpler harness | Extend `evaluation/` to 50 items; retire or wrap `scripts/eval.py`. One eval system only |
| 2 | Latest ADR is 005 | `docs/adrs/` has 001–006, **and** `evaluation/docs/adr/` also has an ADR-006 (collision) | Renumber/merge in Phase 0; next free is 007 |
| 3 | Azure is out of scope | Azure OpenAI is a validated config-only provider (ADR-006) | Keep as proof of portability; run the eval on both providers (see D3) |
| 4 | E-23 needs sourcing | E-23 is seeded (a few chunks, 15 total across 10 frameworks) | Phase 1 is a versioned re-ingest, not a first load; live demo must not break during cutover |
| 5 | Plan is additive to BUILD_PLAN.md | CLAUDE.md: "anything not in BUILD_PLAN.md — stop and flag" | Merge this plan into BUILD_PLAN.md as Phases 4+ at the end of Phase 0 |
| 6 | Auth not mentioned | Time-limited admin access codes exist (`generate_access_code.py`) | Treat as identity source for roles in Phase 5 (see C2) |
| 7 | CI = lint+tests only | `ci.yml` runs ruff on `src/ tests/` and pytest; 6 test files, all mocked; no eval, no security, no type check | Phase 2 adds eval smoke test, not Phase 6 |

### A2. Technical gaps in the current system (evidence from repo)
- **Audit log is append-only by trigger only.** The table owner can drop the triggers; there is no hash chain,
  so tampering is *prevented in normal use* but not *detectable*. Weak claim for a "governed" system.
- **No ACL columns / roles** on `documents`; guardrails are input/output screens, not authorization.
- **Retrieval is dense-only**, tiny corpus (15 chunks), no structure-aware chunking, no provenance metadata
  (version, effective date, section path). Any benchmark on 15 chunks is meaningless.
- **Eval is 15 items, no retrieval metrics** (no Recall@k/MRR), no latency/cost metrics, no pinned run config.
- **No reproducibility:** prompts inline, no corpus hash, no run folder committed.
- **Tracing is external SaaS only;** no request-ID correlation between logs, audit rows and LangSmith traces.
- **Rate limiting is per-IP in memory** (slowapi): resets on redeploy, bypassable behind proxies unless
  `X-Forwarded-For` handling is verified.
- **Single point of failure per dependency** with retry but no degradation path (Neon down, OpenRouter 429 storm).
- **The HITL gate is a button, not a policy.** No risk tiering: every action needs the same approval, no
  approver identity beyond the session, no four-eyes for high-impact actions, no expiry on proposals.

### A3. Gaps in PLAN.md itself
- Golden set of 50 with categories of 5 gives ±1-question swings of 20 points. Needs counts and bootstrap CIs,
  not bare percentages.
- No judge-noise tolerance defined ("within judge noise"). Define it (e.g. ±0.05, 3 baseline runs).
- Phase 4 omits Faiz's review time (confirming obligations by hand is the real cost). Scope to **one**
  guideline (E-23) and budget the review hours.
- `pg_search` BM25 is almost certainly unavailable on Neon; the "hybrid" arm will be `tsvector` FTS. Label it so.
- No rollback / "demo stays up" check per phase although `main` auto-deploys.
- No data-lifecycle story (re-ingest on new guideline version; what happens to old citations?).
- No cost-of-governance measurement (what the controls cost in latency/$ — the question every CTO asks).

## B. What would make this compelling as a portfolio piece

The strongest pitch is not "a RAG agent". It is: **"a governed agent whose controls are tested, measured and
mapped to the regulation it operates under — and I can show you the numbers."** New additions that serve that:

1. **Regulatory change-impact mode (headline feature).** Diff two versions of a guideline (e.g. E-23 draft vs final,
   B-13 revisions) → list changed obligations → map to controls/gaps → Action Agent proposes tickets. This is what
   a bank actually pays for, and it reuses the canonical layer, versioning and HITL. A 60-second demo beats any
   benchmark table.
2. **Tamper-evident audit log.** Hash-chain each audit row (`prev_hash`, `row_hash`), add a `verify_chain`
   endpoint/CLI and a test that mutates a row and shows detection. Closes the weakest governance claim cheaply.
3. **Policy-as-code for actions.** Risk-tier proposed actions (read / low / high) in a YAML policy; high-risk needs
   named approver + reason, proposals expire, rejections require a reason. Test matrix proves no bypass.
4. **Cost-of-governance table.** Run eval with guardrails/audit/HITL on vs off; report added latency, tokens, $.
   Rare, quantitative, and directly useful to a decision-maker.
5. **Public evidence page.** `/evidence` route (or static page) rendering the latest committed eval run, control
   matrix and threat-model summary, each number linked to its run folder. Interviewers can verify without a call.
6. **Provider-portability result.** Same golden set on OpenRouter/GLM and Azure OpenAI; report quality, latency,
   cost deltas. Turns ADR-006 from a claim into a measurement.
7. **Trace-to-evidence link in the UI.** Each answer shows its citations with section path + corpus version, and a
   "view audit trail" link for that request ID. Makes governance visible in the demo itself.
8. **Red-team report.** Prompt-injection and exfiltration suite with published pass rate *and* the failures found
   and fixed (before/after). Honest failures read as senior judgement.
9. **Abstention as a first-class metric.** Headline "refuses correctly X% of the time when the corpus lacks the
   answer, falsely refuses Y%". Highly relevant to regulated use and under-reported in most RAG demos.
10. **Production-gap matrix with effort at 500 / 5,000 users** (kept from PLAN.md) plus a 1-page "what I'd do
    differently with a real bank's constraints" (data residency, model risk validation, SR 11-7 / E-23 lifecycle).

Considered and rejected (scope creep, weak signal/effort): fine-tuning, a second vector DB, knowledge-graph DB,
multi-tenant SaaS features, fancy front-end rewrite.

### B2. Reference-architecture additions (no new infrastructure)
Everything below runs on what already exists: Neon Postgres, the Railway service, OpenRouter (cheap model),
GitHub Actions. No new database, queue or service. The aim is to turn the canonical layer from a lookup table
into a **regulatory knowledge model**.

**Core (folded into the phases in section C)**
| ID | Addition | What it does | Phase | Extra cost |
|---|---|---|---|---|
| R1 | Cross-framework crosswalk | Each canonical obligation links to equivalent requirements in NIST AI RMF, ISO/IEC 42001 and the EU AI Act (already seeded). "Comply once, show many." Traversed with recursive CTEs, no graph DB | 4b | $0 |
| R2 | Applicability engine | An institution profile (FRFI type, size, AI model use, third-party reliance) decides which obligations apply and at what intensity. Encodes E-23 proportionality as YAML/SQL rules | 4b | $0 |
| R3 | Bitemporal corpus | Every guideline, section and obligation carries valid time (effective dates) and recorded time (ingested/superseded). Answers "what applied on date X" and "what did the agent know when it answered" | 1, 4a | $0 |
| R4 | Decision record and replay | Each answer persists prompt version, model ID, retrieved chunk IDs, corpus version, applicability result and policy decisions; a replay command re-runs it and diffs the output | 5 | $0 |
| R5 | Transactional outbox for tickets | `/execute` writes the approved action to an outbox table in the same transaction as the audit row; a worker creates the ticket exactly once with retries and an idempotency key | 5 | $0 |

**Next tier (in phases, cut-able)**
| ID | Addition | What it does | Phase | Extra cost |
|---|---|---|---|---|
| R6 | Claim-level grounding check | Splits the answer into claims, checks each against its cited section, flags or strips unsupported claims. Upgrades `is_cited` from "has a citation" to "the citation supports it" | 3 | Small token cost, cheap model |
| R7 | Regulatory change watcher | Scheduled GitHub Actions job checks OSFI pages for new versions and opens a change-impact run under HITL. Closes golden-workflow step 1 without a manual trigger | 6 | $0 |
| R8 | The agent as a governed model | Its own E-23 model-inventory entry: model card, risk rating, validation report generated from eval runs, change log for prompts and models | 10 | $0 |
| R9 | Typed answer contract | One schema for every answer (claims, citations, effective dates, confidence, abstain reason) shared by UI, eval and audit | 2 | $0 |

**Backlog (only if time allows)**
- Compliance posture register: per-obligation control/evidence status updated by approved tickets, event-sourced from the audit log.
- Semantic cache keyed by corpus version (reduces spend).
- Reviewer feedback loop feeding golden-set candidates.
- MCP server exposing the canonical tools to any MCP client.
- Reversible PII tokenisation before LLM calls, mapping held in Postgres.

## C. Revised phases

| Phase | Name | Effort | Depends | Outcome |
|---|---|---|---|---|
| 0 | Discovery, baseline, repo reconciliation | 0.5–1 d | — | `docs/CURRENT_STATE.md`, `baseline-v0` tag, ADR renumbered, plans merged |
| 1 | Corpus: versioned, bitemporal, structure-aware ingest | 1.5–2.5 d | 0 | E-23, B-10, B-13 with provenance and valid/recorded time (R3); corpus report; **two versions of at least one guideline** (needed for #1) |
| 2 | Eval harness v2 (extend `evaluation/`) + CI smoke | 2.5–3.5 d | 1 | 50-item set, retrieval + RAGAS + abstention + latency/cost, typed answer contract (R9), run folders, CIs, CI smoke test |
| 3 | Retrieval and grounding experiments | 3–4 d | 2 | dense vs tsvector-hybrid vs rerank, plus claim-level grounding check (R6), per-category numbers; ADR |
| 4a | Canonical entity layer (E-23 only) | 4–5 d + review hrs | 3 | typed, bitemporal model + tools; benchmark vs Phase 3 winner; ADR |
| 4b | Crosswalk and applicability | 3–4 d + review hrs | 4a | E-23 obligations mapped to NIST AI RMF / ISO 42001 / EU AI Act (R1); institution-profile applicability rules (R2); ADR |
| 5 | Governance hardening | 4–5 d | 2 | ACL-at-retrieval, hash-chained audit, decision record + replay (R4), ticket outbox (R5), policy-as-code HITL, injection suite, threat model, control matrix |
| 6 | **Change-impact mode** | 4–5 d | 1, 4a, 4b | version diff → impacted obligations → applicable controls → ticket proposals under HITL; scheduled change watcher (R7); demoable in UI |
| 7 | Reliability & failure injection | 1–2 d | 2 | degradation paths, runbook, request-ID correlation |
| 8 | Portability & cost-of-governance runs | 1–2 d | 2, 5 | Azure vs OpenRouter table; controls on/off table |
| 9 | *(Optional)* Gateway as control plane | 2–3 d | 3, 7 | flag-gated routing, overhead measured |
| 10 | Dossier + public evidence page | 3–4 d | all | diagrams, ADRs, gap matrix, case study, the agent's own E-23 model-inventory entry (R8), `/evidence`, README leads with results |

Total effort: about 27.5–38 days without Phase 9 (29.5–41 with it), plus Faiz's review hours.
Parallel: 5 and 7 can run alongside 4a/4b. Phase 6 is the one to protect if time is short; if forced to cut,
cut 9 first, then the rerank arm of 3, then 8, then R7 and R6. R1–R5 are not cut: they are the architecture story.

### Phase notes (changes vs PLAN.md only)
- **P0:** also resolve ADR-006 collision; check Neon storage quota and pgvector/`tsvector` support; record whether
  slowapi trusts `X-Forwarded-For`; confirm Python/Ruff/black versions; list every place the plan didn't match.
- **P2:** pin tolerance and CI method up front: 3 baseline runs, report mean ± range, bootstrap CIs on
  retrieval metrics, show raw counts per category. Pre-register the success criteria for P3/P4 *before* running them
  (e.g. "hybrid must improve exact-identifier Recall@5 by ≥0.10 without regressing conceptual by >0.03") so the
  write-up can't be accused of cherry-picking. Prompts to files. CI smoke test on 10 items with a cost cap.
- **P1:** bitemporal columns from the start (`valid_from`, `valid_to`, `recorded_at`, `superseded_at`) so later
  phases never need a backfill. Superseded rows are kept, never overwritten.
- **P2:** the typed answer contract (R9) lands here because the eval, UI and audit all read it.
- **P3:** grounding check (R6) is measured as its own arm: unsupported-claim rate with and without it, plus the
  added latency and tokens. Uses the cheap judge model.
- **P4a:** E-23 only; LLM proposes, rules validate, Faiz confirms in batches; budget ~4–6 review hours explicitly.
  Entity extraction output is cached and versioned so evals don't re-pay. Entities inherit bitemporal columns.
- **P4b:** crosswalk links carry a relation type (`equivalent`, `partial`, `related`) and the same
  proposed/confirmed/rejected status as obligations; only confirmed links are used. Applicability rules live in
  versioned YAML and are evaluated in SQL; ship 2–3 synthetic institution profiles (clearly labelled synthetic) and
  golden cases asserting which obligations apply to each. New typed tools: `get_crosswalk(obligation_id)`,
  `get_applicable_obligations(profile_id, as_of)`. Budget ~2–3 more review hours for crosswalk confirmation.
- **P5:** add (a) hash-chain with `verify_chain` and a tamper test, (b) action risk-tier YAML with expiry and
  named approver, (c) roles derived from access-code claims, (d) assertion that restricted text never appears in
  LangSmith traces (redact/disable input capture for restricted sessions), (e) PII-in-logs test. Control matrix
  maps each control → test → NIST AI RMF function → OSFI E-23 expectation, with honest status labels.
  Also (f) decision record per request (R4) with a `replay <request_id>` command and a test that a replay with the
  same pinned config reproduces the stored retrieval set, and (g) ticket outbox (R5) with tests for double-click,
  worker crash and retry producing exactly one ticket.
- **P6 (new):** requires P1 to hold two versions of a guideline. Output is a structured impact report (changed /
  added / removed obligations, the profiles they apply to, affected controls and crosswalked frameworks, proposed
  tickets). Eval it: golden set of ~10 change-impact cases with expected changed obligations; report
  precision/recall of detected changes. The change watcher (R7) runs as a weekly GitHub Actions cron that only
  detects and records a new version; ingesting it and opening tickets still goes through HITL.
- **P8 (new):** cheap but high-signal; reuses the P2 harness with config flags.
- **P10:** `/evidence` page built from committed run JSON, not hand-typed numbers. The model-inventory entry (R8)
  is generated from the same run data and labelled as a self-assessment, not an independent validation.

## D. Decisions needed from Faiz
1. **Guideline versions for P6:** which guideline has two official versions to diff (E-23 draft vs final is the
   natural pair; confirm OSFI still hosts the draft, otherwise supply the file)?
2. **Reranker:** local cross-encoder (memory risk on Railway Hobby) vs hosted API (text leaves boundary; corpus is
   public). Decide at P3.
3. **Provider comparison:** is a funded Azure OpenAI deployment still available for P8?
4. **Review budget:** can you commit ~4–6 hours for obligation confirmation, ~2–3 hours for crosswalk confirmation
   and ~2 hours for golden-set verification?
5. **Order:** run P6 immediately after P1/P2 as a thin vertical slice (more compelling sooner), or keep strict order?
   Recommendation: strict through P3, then P4a/P4b and P5 in parallel, P6 after.
6. **Crosswalk scope (P4b):** map E-23 to all three seeded AI frameworks (NIST AI RMF, ISO/IEC 42001, EU AI Act),
   or start with NIST AI RMF only? Recommendation: NIST first, the others if review time allows.
7. **Institution profiles (P4b):** which 2–3 synthetic profiles? Suggested: large domestic bank, small FRFI with
   limited model use, insurer relying heavily on third-party models.

## E. Risks
1. Phase 4a/4b review burden and LLM extraction quality → scope to E-23, crosswalk to NIST first, accept lower
   coverage, report it.
2. Corpus cutover breaks live demo → ingest into new versioned tables, flag-switch, keep old rows until verified.
3. Free/cheap model variance inflates judge noise → fixed judge model, 3 runs, state tolerance.
4. Neon free tier storage/compute limits → measure in P0, size entity tables accordingly.
5. Scope creep from the "compelling" list → B1–B3 and R1–R5 are core; B4–B9 and R6–R9 are cut-able; backlog only
   if time allows.
6. Crosswalk links presented as authoritative → every link shows its relation type and confirmation status; docs
   state the crosswalk is the author's interpretation, not an official OSFI or NIST mapping.
7. Applicability rules mistaken for compliance advice → profiles are labelled synthetic; UI and docs state the
   output is a reference implementation, not legal or regulatory advice.
