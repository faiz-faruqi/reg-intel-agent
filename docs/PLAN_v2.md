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
multi-tenant SaaS features, fancy front-end rewrite, MCP server for the corpus (nice-to-have, post-dossier).

## C. Revised phases

| Phase | Name | Effort | Depends | Outcome |
|---|---|---|---|---|
| 0 | Discovery, baseline, repo reconciliation | 0.5–1 d | — | `docs/CURRENT_STATE.md`, `baseline-v0` tag, ADR renumbered, plans merged |
| 1 | Corpus: versioned, structure-aware ingest | 1–2 d | 0 | E-23, B-10, B-13 with provenance; corpus report; **two versions of at least one guideline** (needed for #1) |
| 2 | Eval harness v2 (extend `evaluation/`) + CI smoke | 2–3 d | 1 | 50-item set, retrieval + RAGAS + abstention + latency/cost, run folders, CIs, CI smoke test |
| 3 | Retrieval experiments | 2–3 d | 2 | dense vs tsvector-hybrid vs rerank with per-category numbers; ADR |
| 4 | Canonical entity layer (E-23 only) | 4–5 d + review hrs | 3 | typed model + tools; benchmark vs Phase 3 winner; ADR |
| 5 | Governance hardening | 3–4 d | 2 | ACL-at-retrieval, hash-chained audit, policy-as-code HITL, injection suite, threat model, control matrix |
| 6 | **Change-impact mode** | 3–4 d | 1, 4 | version diff → impacted obligations → gap/ticket proposals under HITL; demoable in UI |
| 7 | Reliability & failure injection | 1–2 d | 2 | degradation paths, runbook, request-ID correlation |
| 8 | Portability & cost-of-governance runs | 1–2 d | 2, 5 | Azure vs OpenRouter table; controls on/off table |
| 9 | *(Optional)* Gateway as control plane | 2–3 d | 3, 7 | flag-gated routing, overhead measured |
| 10 | Dossier + public evidence page | 2–3 d | all | diagrams, ADRs, gap matrix, case study, `/evidence`, README leads with results |

Parallel: 5 and 7 can run alongside 4. Phase 6 is the one to protect if time is short; if forced to cut,
cut 9 first, then the rerank arm of 3, then 8.

### Phase notes (changes vs PLAN.md only)
- **P0:** also resolve ADR-006 collision; check Neon storage quota and pgvector/`tsvector` support; record whether
  slowapi trusts `X-Forwarded-For`; confirm Python/Ruff/black versions; list every place the plan didn't match.
- **P2:** pin tolerance and CI method up front: 3 baseline runs, report mean ± range, bootstrap CIs on
  retrieval metrics, show raw counts per category. Pre-register the success criteria for P3/P4 *before* running them
  (e.g. "hybrid must improve exact-identifier Recall@5 by ≥0.10 without regressing conceptual by >0.03") so the
  write-up can't be accused of cherry-picking. Prompts to files. CI smoke test on 10 items with a cost cap.
- **P4:** E-23 only; LLM proposes, rules validate, Faiz confirms in batches; budget ~4–6 review hours explicitly.
  Entity extraction output is cached and versioned so evals don't re-pay.
- **P5:** add (a) hash-chain with `verify_chain` and a tamper test, (b) action risk-tier YAML with expiry and
  named approver, (c) roles derived from access-code claims, (d) assertion that restricted text never appears in
  LangSmith traces (redact/disable input capture for restricted sessions), (e) PII-in-logs test. Control matrix
  maps each control → test → NIST AI RMF function → OSFI E-23 expectation, with honest status labels.
- **P6 (new):** requires P1 to hold two versions of a guideline. Output is a structured impact report (changed /
  added / removed obligations, affected controls, proposed tickets). Eval it: golden set of ~10 change-impact
  cases with expected changed obligations; report precision/recall of detected changes.
- **P8 (new):** cheap but high-signal; reuses the P2 harness with config flags.
- **P10:** `/evidence` page built from committed run JSON, not hand-typed numbers.

## D. Decisions needed from Faiz
1. **Guideline versions for P6:** which guideline has two official versions to diff (E-23 draft vs final is the
   natural pair; confirm OSFI still hosts the draft, otherwise supply the file)?
2. **Reranker:** local cross-encoder (memory risk on Railway Hobby) vs hosted API (text leaves boundary; corpus is
   public). Decide at P3.
3. **Provider comparison:** is a funded Azure OpenAI deployment still available for P8?
4. **Review budget:** can you commit ~4–6 hours for obligation confirmation and ~2 hours for golden-set verification?
5. **Order:** run P6 immediately after P1/P2 as a thin vertical slice (more compelling sooner), or keep strict order?
   Recommendation: strict through P3, then P5 and P4 in parallel, P6 after.

## E. Risks (top five)
1. Phase 4 review burden and LLM extraction quality → scope to E-23, accept lower coverage, report it.
2. Corpus cutover breaks live demo → ingest into new versioned tables, flag-switch, keep old rows until verified.
3. Free/cheap model variance inflates judge noise → fixed judge model, 3 runs, state tolerance.
4. Neon free tier storage/compute limits → measure in P0, size entity tables accordingly.
5. Scope creep from the "compelling" list → B1–B3 are core; B4–B9 each ≤0.5 day and cut-able; B10 is docs.
