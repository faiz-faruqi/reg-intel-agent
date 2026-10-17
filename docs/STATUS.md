# Status — Plan v2 execution

Living log. Update at the start and end of every phase (rule 1.2 in `docs/PLAN_v2.md`).
Newest entries at the top of each section. Dates are YYYY-MM-DD.

**Last updated:** 2026-10-17 (end of Phase 0, handover pack added)

## Phase status

| Phase | Status | Branch | PR | Notes |
|---|---|---|---|---|
| 0 Discovery | Done, PR open, awaiting review | `phase-0-discovery` | faiz-faruqi/reg-intel-agent#3 | Docs and a read-only SQL script only; merge doesn't change demo behaviour |
| H API governance hotfix | Proposed, **awaiting approval** | `hotfix-api-governance` | — | See PLAN_v2 §5 Phase H |
| 1 Corpus | Not started (needs probe output and the Phase 1 brief approved) | `phase-1-corpus` | — | |
| 2 Eval | Not started | `phase-2-eval` | — | |
| 3 Retrieval | Not started | `phase-3-retrieval` | — | |
| 4a Canonical | Not started | `phase-4a-canonical` | — | |
| 4b Crosswalk | Not started | `phase-4b-crosswalk` | — | |
| 5 Governance | Not started | `phase-5-governance` | — | |
| 6 Change-impact | Not started | `phase-6-change-impact` | — | |
| 7 Reliability | Not started | `phase-7-reliability` | — | |
| 8 Portability | Not started | `phase-8-portability` | — | |
| 9 Gateway (optional) | Not started | `phase-9-gateway` | — | Needs separate approval |
| 10 Dossier | Not started | `phase-10-dossier` | — | |

## Waiting on Faiz

| # | Item | Why it blocks | How |
|---|---|---|---|
| 1 | Push tag `baseline-v0` | The agent's git proxy refused tag pushes | `git fetch origin && git tag -a baseline-v0 63fcb80 -m "Baseline before PLAN_v2" && git push origin baseline-v0` |
| 2 | Run the Neon probe | Fills `CURRENT_STATE.md` §9; Phase 1 and 3 depend on it (`pg_search` vs `tsvector`, storage, row count) | `psql "$DATABASE_URL" -f scripts/neon_probe.sql > neon_probe.out 2>&1` (postgresql:// form) and paste the output |
| 3 | Confirm Railway env | `SESSION_SECRET`, `DEMO_PASSWORD`, `ADMIN_KEY` must not be the public code defaults | Check Railway variables; no code change |
| 4 | Approve or decline Phase H hotfix | Live API skips guardrails and trusts the `/execute` body | Reply "approve hotfix" or "skip" |
| 5 | Approve doc corrections | `BUILD_PLAN.md` and `CLAUDE.md` have stale facts | `CURRENT_STATE.md` §14 lists them |
| 6 | Review and merge PR #3 | Phase 1 branches from `main` once merged | GitHub |

## Open decisions

| # | Decision | Recommendation | Needed by |
|---|---|---|---|
| D1 | Guideline versions for change-impact | E-23 draft vs 2025 final, if OSFI still hosts the draft; otherwise Faiz supplies the file | Phase 1 |
| D2 | Reranker: local cross-encoder vs hosted API | Decide at Phase 3 with measured memory and latency | Phase 3 |
| D3 | Azure OpenAI deployment available for comparison? | — | Phase 8 |
| D4 | Review time commitment (§7 of the plan) | — | Phase 2 |
| D5 | Crosswalk scope | NIST AI RMF first; ISO 42001 and EU AI Act if time allows | Phase 4b |
| D6 | Institution profiles | Large domestic bank; small FRFI with limited model use; insurer relying on third-party models | Phase 4b |
| D7 | Migration tooling | Numbered SQL files + `schema_migrations` table (no new dependency); Alembic is the alternative | Phase 1 |

## Decision log

| Date | Decision | By |
|---|---|---|
| 2026-10-16 | Per-phase branches named in PLAN_v2 §4; PR per phase; nothing merges without approval | Faiz |
| 2026-10-16 | Faiz runs the Neon probe himself (no DB credentials in agent environments) | Faiz |
| 2026-10-16 | Baseline tag `baseline-v0` on `63fcb80` (live `main`) | Faiz (agent recommendation) |
| 2026-10-16 | Assurance ADR renumbered ADR-007; next free ADR-008 | Agent, Phase 0 |
| 2026-10-15 | No infrastructure scaling; add R1–R9 reference-architecture items on existing infra | Faiz |
| 2026-10-15 | No client; target is a production-grade reference implementation, honestly framed | Faiz |
| 2026-10-13 | Adopt PLAN_v2 (gap analysis + additions) over the original PLAN.md | Faiz |

## Environment notes for agents

- Agent cloud sessions have **no** `DATABASE_URL` or `OPENROUTER_API_KEY`. Anything needing the live DB or a
  live model run must be done by Faiz, or credentials added to that environment's secrets with his approval.
- The agent git proxy allowed branch pushes but **refused tag pushes** (2026-10-16).
- Local Postgres for testing: `docker compose up postgres` (pgvector/pgvector:pg16), or a local Postgres 16
  with the `postgresql-16-pgvector` package. `scripts/neon_probe.sql` was validated that way.
- A private roadmap page published on claude.ai on 2026-10-13 is out of date. Ignore it; this file and
  `docs/PLAN_v2.md` are authoritative.
