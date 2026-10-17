# Interview Notes

Talking points recorded at the end of each phase of `docs/PLAN_v2.md`: what was decided, what the
numbers showed, and what was surprising.

## Phase 0 — Discovery and baseline

- **Audit the claims before building on them.** Reading the code found two governance controls the
  docs describe as working that the live API does not apply: guardrails only run in the CLI, and the
  UI's Approve button sends a ticket body the server trusts. The lesson for system design is to treat
  "the docs say it's governed" as a hypothesis and trace each control to the request path that
  enforces it.
- **A human-approval gate has to be bound to what was approved.** Approving in the browser and then
  sending the content separately lets the approved and executed actions diverge. The fix is a
  server-issued, signed proposal that is the only thing `/execute` accepts.
- **Behind a proxy, per-IP rate limiting can turn into one shared limit.** Without trusting the
  proxy's forwarded-for header, every visitor shares Railway's proxy address and one bucket.
- **Mock scores aren't a baseline.** The assurance framework's mock run gives tidy numbers
  (faithfulness 0.86) from synthetic answers. They prove the pipeline runs, not that the agent is
  good, so the first real baseline waits for Phase 2.
- **Reproducibility starts with dependencies.** With no lockfile, two builds of the same commit can
  run different LangChain versions, so an eval result can't be tied to a commit until versions are pinned.
