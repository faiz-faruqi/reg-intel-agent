# Agent instructions

Start with `docs/HANDOVER.md`. It lists the files to read, in order, and how work is done in this repo.

Non-negotiables (details in `CLAUDE.md` and `docs/PLAN_v2.md` §1):
- Post the phase brief and wait for the owner's "go" before each phase.
- One branch and one PR per phase; never merge to `main` (it auto-deploys the live demo).
- Never change production env vars or deploy. Secrets only from env vars.
- No fabricated regulatory text; only the owner verifies golden answers and confirms canonical links.
- Every published number must come from a saved, committed run.
