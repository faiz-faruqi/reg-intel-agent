# Handover — start here

This repository is executing **Plan v2**: turning a working governed RAG agent demo into an evidence-backed
reference implementation. Any coding agent can pick the work up from these files alone; no chat history is
needed.

## 1. Read in this order

| # | File | What it gives you |
|---|---|---|
| 1 | `CLAUDE.md` | Project identity, architecture as built, non-negotiable governance and security rules |
| 2 | `docs/HANDOVER.md` (this file) | How to work here |
| 3 | `docs/STATUS.md` | **Where things stand:** phase status, open PRs, what's waiting on Faiz, decisions made |
| 4 | `docs/PLAN_v2.md` | The plan: working rules (§1, mandatory), phase specs (§5) and order (§4) |
| 5 | `docs/CURRENT_STATE.md` | As-built baseline with evidence: schema, routes, corpus, gaps, versions |
| 6 | `docs/adrs/` and `evaluation/docs/adr/` | Decisions already made (ADR-001 to 007; next is 008) |
| 7 | `docs/interview-notes.md` | Talking points per phase (append at each phase end) |

Background only, not instructions: `BUILD_PLAN.md` (history of Phases 0–3 of the original build; some facts
are stale, see `CURRENT_STATE.md` §14), `README.md`, `evaluation/README.md`, `docs/demo-script.md`.

If these files disagree: `docs/STATUS.md` wins on current state and decisions, `docs/PLAN_v2.md` on scope and
rules, `CLAUDE.md` on security and governance constraints. Flag any conflict to Faiz instead of choosing.

## 2. Starting a session

1. `git fetch origin` and check open PRs and branches against `docs/STATUS.md`.
2. Find the next phase whose dependencies are met and that isn't blocked by a "Waiting on Faiz" item.
3. Post the phase brief (PLAN_v2 §1.1) and **wait for "go"**. Do not write code before that.
4. Branch from the latest `main` using the branch name in PLAN_v2 §4.
5. Set the phase to "In progress" in `docs/STATUS.md` as the first commit on the branch.

## 3. Ending a phase

1. Lint and tests pass locally: `ruff check src/ tests/` and `pytest`.
2. Re-read the diff for anything that changes live-demo behaviour without a flag defaulting to the old
   behaviour. A merge to `main` is a deploy.
3. Update `docs/STATUS.md` (status, PR link, decisions made, new open questions), append to
   `docs/interview-notes.md`, and update `docs/CURRENT_STATE.md` if the architecture changed.
4. Open one PR into `main` with: what changed, how it was verified, impact on the live demo, anything left
   undone. Do not merge it.

## 4. Commands

```bash
pip install -e ".[dev]"                     # Python 3.11+
ruff check src/ tests/                      # CI lint
pytest                                      # 43 mocked tests at baseline
docker compose up                           # local FastAPI + Postgres/pgvector (needs .env, see .env.example)
python -m src.ingest                        # seed the legacy corpus (needs an embedding key)
python -m src.cli "question"                # full graph with the CLI approval gate
cd evaluation && python run_assurance.py --mode mock   # pipeline check only; scores are synthetic
psql "$DATABASE_URL" -f scripts/neon_probe.sql         # read-only DB probe (Faiz runs this against Neon)
```

## 5. Things that will trip you up

- **Railway deploys `main` automatically.** Never merge; never change Railway env vars.
- **No live credentials** in agent environments (no `DATABASE_URL`, no model key). Ask Faiz for runs that
  need them, and print a cost estimate first (ask if a run may exceed US$5).
- **Guardrails and the `/execute` approval binding are weaker on the API than the docs claim** until Phase H
  ships. Don't build on them as if they work. See `CURRENT_STATE.md` §7.
- **The current corpus is authored summaries, not official text.** Don't use it for benchmark numbers.
- **Mock eval scores are synthetic.** Never report them as results.
- **Only Faiz confirms** golden answers (`verified_by`), obligations, crosswalk links and applicability.
- **Tag pushes were refused** by the agent git proxy; branch pushes work.

## 6. Prompt to give a new agent

> You are continuing work on this repository. Read, in order: `CLAUDE.md`, `docs/HANDOVER.md`,
> `docs/STATUS.md`, `docs/PLAN_v2.md`, `docs/CURRENT_STATE.md`. Follow the working rules in PLAN_v2 §1
> exactly. Using STATUS.md, identify the next phase that is unblocked, then post the phase brief from
> PLAN_v2 §1.1 and wait for my "go" before changing anything.
