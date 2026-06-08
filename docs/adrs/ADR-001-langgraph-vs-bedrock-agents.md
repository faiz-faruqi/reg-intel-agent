# ADR-001: LangGraph vs. Amazon Bedrock Agents

## Status
Accepted

## Context

This system requires a multi-agent orchestration layer that:
- Routes a compliance question through three specialist agents in sequence
- Maintains shared typed state across agent transitions (retrieved chunks, draft
  response, proposed action, approval decision)
- Pauses execution at a human approval gate before any write action executes
- Writes every step to an immutable audit log
- Runs on Railway (not AWS compute), so managed AWS services requiring VPC or
  IAM roles are not viable without significant additional infrastructure

Two orchestration options were evaluated:

### Option A — Amazon Bedrock Agents (managed)
AWS's fully managed multi-agent framework. Handles routing, memory, tool
invocation, and observability natively within the AWS ecosystem.

**Pros:**
- Zero orchestration ops — AWS manages the runtime
- Native integration with Bedrock models, Bedrock Knowledge Bases, and Guardrails
- Built-in tracing and audit via CloudWatch
- Handles agent collaboration patterns (supervisor → sub-agent) out of the box

**Cons:**
- Requires AWS compute (Lambda or ECS) to host agent logic — not viable on Railway
- Human-in-the-loop requires a custom Lambda approval flow; no native `interrupt`
  primitive equivalent to LangGraph's `interrupt_before`
- State is opaque — the framework manages it internally, making custom audit
  log writes and guardrail injection harder to place precisely in the graph
- Vendor lock-in: graph definition, state schema, and routing logic are all
  Bedrock-specific. Porting to another provider requires a rewrite.
- Cannot be tested locally without AWS credentials and deployed infrastructure

### Option B — LangGraph (self-orchestrated)
An open-source Python library for building stateful, graph-based agent workflows.

**Pros:**
- Full control over state schema (`AgentState` TypedDict), routing logic, and
  node placement — audit log writes and guardrail checks can be injected anywhere
- `interrupt_before=["human_gate"]` is a first-class primitive — the graph pauses,
  state is checkpointed, and execution resumes after `update_state()`. This is
  exactly the HITL pattern required.
- Runs anywhere Python runs — local, Railway, Docker, AWS — no infrastructure
  dependency
- Fully portable: the graph definition, agents, and state are plain Python.
  Swapping model providers (OpenRouter → Bedrock) is a client configuration
  change, not a graph rewrite.
- LangSmith tracing integrates via environment variables — no code changes

**Cons:**
- Self-managed: the team is responsible for graph correctness, checkpointing,
  and failure handling
- No managed scaling or built-in retry at the orchestration layer (mitigated by
  per-call retries on the model client)

## Decision

**LangGraph** — Option B.

The human-in-the-loop gate is the centrepiece of the governance story. LangGraph's
`interrupt_before` makes this a first-class, testable primitive. Bedrock Agents has
no equivalent without a custom Lambda approval flow, which adds infrastructure
complexity that defeats the cost and simplicity goals of the demo tier.

Additionally, running on Railway (not AWS compute) makes Bedrock Agents impractical
without a VPC + Lambda setup that is explicitly out of scope for this phase.

### Graph design
Two compiled graphs are maintained:

- `graph` (`src/graph.py`) — read-only, used by the API (`POST /query`). Runs
  Knowledge + Analysis agents only. No HITL, no Action Agent.
- `propose_graph` (`src/graph.py`) — full 3-agent graph, no HITL. Used by
  `POST /propose` to demonstrate the Action Agent proposal via the live URL.
- CLI graph (`src/cli.py`) — full governance workflow with `interrupt_before=
  ["human_gate"]`. Used by `python -m src.cli`. Requires a human at the terminal.

## When Bedrock Agents wins

In a production AWS engagement where:
- All compute is already in AWS (ECS, Lambda, App Runner)
- The team wants zero orchestration ops and native CloudWatch audit trails
- Bedrock Knowledge Bases replace the pgvector retrieval layer
- The additional AWS cost is justified by operational simplicity and SLA guarantees

The migration path is: replace `src/graph.py` with a Bedrock Agents definition;
replace `src/db.py` similarity search with a Knowledge Base retrieval call;
keep `src/guardrails.py` or replace with a Bedrock Guardrails config.
Application agents and state schema are reusable.

## Consequences

- **Positive:** Full control over state, routing, and audit injection. HITL gate
  works locally and on Railway with no external dependencies. Fully portable.
- **Positive:** LangSmith tracing is drop-in — same observability story as Bedrock.
- **Negative:** Team owns orchestration correctness. Graph must be tested explicitly.
- **Negative:** No managed scaling at the orchestration layer — acceptable at demo
  volume, re-evaluate if throughput requirements grow.
