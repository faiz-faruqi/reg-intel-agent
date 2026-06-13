# ADR-006: Enterprise AI Assurance Framework as a Standalone Evidence Layer

- **Status:** Accepted
- **Date:** 2026-06-10
- **Context owner:** CloudKraft Consulting (reference implementation)

## Context

The Regulatory Intelligence Agent (ADR-001 through ADR-005) demonstrates a
governed, multi-agent RAG system with human-in-the-loop approval, an immutable
audit log, and Bedrock-compatible guardrails. What it did not yet have was a
repeatable way to *evidence* that those controls work — quantitatively, against
the system's actual outputs, in a form a model-risk function or regulator would
recognize.

Canadian federally regulated financial institutions are inside the transition
window for OSFI Guideline E-23 (Model Risk Management), effective 1 May 2027,
which extends model-risk expectations explicitly to AI/ML systems. Comparable
expectations exist in the NIST AI Risk Management Framework, ISO/IEC 42001, and
the EU AI Act. Across all of them the recurring gap is the same: organizations
can describe controls but struggle to produce repeatable, output-level evidence
that the controls hold.

## Decision

Build the assurance capability as a **separate evidence layer** that treats the
Agent as a system-under-test, rather than embedding evaluation inside the Agent.

The layer:

1. Runs a curated **golden dataset** through the system-under-test.
2. Scores answerable items with **RAGAS** (faithfulness, answer relevancy,
   context precision, context recall) and scores out-of-scope items on
   **refusal correctness**.
3. Assesses architectural controls (human oversight, audit logging, guardrails)
   as observed activities.
4. Generates an **auto-generated Model Risk Assessment report** with a
   **control-to-framework mapping** (NIST AI RMF and OSFI E-23 in v1; ISO 42001
   and EU AI Act in Phase 2).

The scoring layer is abstracted behind a uniform result structure so the same
suite can run against different model backends — in particular **OpenRouter
(demo)** and **AWS Bedrock (production path)** — producing a comparison. This
makes the Bedrock production path in ADR-005 demonstrable rather than only
documented.

## Alternatives considered

- **Embed evaluation inside the Agent.** Rejected: couples assurance to one
  system and undermines the independence that validation evidence requires.
- **Dashboard-only output (scores, no document).** Rejected: a metrics
  dashboard is an engineer's artifact. The consumable artifact for a model-risk
  committee is a structured assessment document.
- **Framework-specific tool (e.g. an "OSFI E-23 compliance checker").**
  Rejected: narrows the addressable use case to one sector. The engine is
  sector-neutral; regulatory frameworks are a swappable mapping layer.

## Consequences

- **Positive:** Sector-neutral core with FSI-relevant mapping; closes the
  hands-on Bedrock gap; produces a reusable consulting deliverable template;
  separates assurance evidence from the system being assured.
- **Negative / scope limits:** This is a reference implementation that assures
  its *own* system. It is not a client-deployed compliance product, and its
  golden-dataset ground truths require subject-matter review before results are
  used as formal evidence. The adversarial / red-team suite is deferred to
  Phase 2.

## Honest framing

Positioned as: *"a reference implementation of an AI assurance methodology that
produces audit-ready evidence mapped to E-23 and NIST"* — not *"compliance
tooling delivered into a bank."* The differentiator is governance and
evaluation as a first-class architectural concern, demonstrated end to end.
