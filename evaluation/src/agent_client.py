"""
agent_client.py
---------------
Adapter between the assurance harness and the system-under-test.

The harness only depends on the `query()` contract below, so the same
evaluation can run against any LLM application that returns an answer plus the
contexts it retrieved.

Two modes:
  - mock : returns synthetic, deterministic responses so the full pipeline
           (evaluation -> report) can be exercised with no network, no keys,
           and no running Agent. Used to produce the sample report.
  - live : calls the Regulatory Intelligence Agent's HTTP API.

LIVE MODE TODO
  Set AGENT_BASE_URL and AGENT_QUERY_PATH in your .env and confirm the
  request/response shape below matches your FastAPI endpoint. The expected
  contract is:

      POST {AGENT_BASE_URL}{AGENT_QUERY_PATH}
      body:     {"question": "<str>"}
      response: {"answer": "<str>", "contexts": ["<str>", ...]}

  Adjust `_parse_live_response` if your field names differ.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from typing import List


@dataclass
class AgentResponse:
    answer: str
    contexts: List[str] = field(default_factory=list)


class AgentClient:
    def __init__(self, mode: str = "mock", timeout: int = 60):
        self.mode = mode
        self.timeout = timeout
        self.base_url = os.getenv("AGENT_BASE_URL", "").rstrip("/")
        self.query_path = os.getenv("AGENT_QUERY_PATH", "/query")

        if self.mode == "live" and not self.base_url:
            raise ValueError(
                "AGENT_BASE_URL is not set. Set it in your .env to run live mode."
            )

    # -- public contract -------------------------------------------------
    def query(self, question: str, reference_contexts: List[str] | None = None,
              expected_behaviour: str = "answerable") -> AgentResponse:
        if self.mode == "mock":
            return self._mock_query(question, reference_contexts or [], expected_behaviour)
        return self._live_query(question)

    # -- live ------------------------------------------------------------
    def _live_query(self, question: str) -> AgentResponse:
        import requests  # imported lazily so mock mode needs no dependency

        url = f"{self.base_url}{self.query_path}"
        resp = requests.post(url, json={"question": question}, timeout=self.timeout)
        resp.raise_for_status()
        return self._parse_live_response(resp.json())

    @staticmethod
    def _parse_live_response(payload: dict) -> AgentResponse:
        # Field names match the live Regulatory Intelligence Agent response shape:
        #   {"question": "...", "response": "...", "citations": [...], "is_cited": bool}
        # Citations are plain strings e.g. "[2] OSFI E-23 — full citation string"
        answer = payload.get("response") or payload.get("answer") or ""
        contexts = (
            payload.get("citations")
            or payload.get("contexts")
            or payload.get("sources")
            or []
        )
        # Citations are plain strings — no dict unpacking needed.
        # If the shape ever changes to dicts, handle here:
        if contexts and isinstance(contexts[0], dict):
            contexts = [c.get("text") or c.get("content") or c.get("excerpt") or "" for c in contexts]
        return AgentResponse(answer=answer, contexts=contexts)

    # -- mock ------------------------------------------------------------
    def _mock_query(self, question: str, reference_contexts: List[str],
                    expected_behaviour: str) -> AgentResponse:
        """
        Deterministic synthetic behaviour. Most answerable items return a
        grounded answer derived from the reference contexts; a couple are
        intentionally degraded so the sample report has realistic, non-perfect
        results and a meaningful residual-risk section. Out-of-scope items
        correctly refuse.
        """
        if expected_behaviour == "out_of_scope":
            return AgentResponse(
                answer=(
                    "This question falls outside the scope of the regulatory "
                    "guidance available to me, so I cannot provide an answer."
                ),
                contexts=[],
            )

        # Use a stable hash of the question to decide which items are degraded.
        bucket = int(hashlib.sha256(question.encode()).hexdigest(), 16) % 10

        if bucket == 0:
            # Degraded: partially unsupported answer (drops a context).
            answer = (
                "Based on the available guidance, " + (reference_contexts[0] if reference_contexts else "")
                + " Further specifics could not be confirmed from the sources."
            )
            return AgentResponse(answer=answer, contexts=reference_contexts[:1])

        if bucket == 1:
            # Degraded: a small unsupported addition (mild hallucination).
            base = " ".join(reference_contexts) if reference_contexts else ""
            answer = base + " It is also widely expected that penalties will apply immediately, though this is not stated in the source."
            return AgentResponse(answer=answer, contexts=reference_contexts)

        # Healthy: grounded answer that paraphrases the reference contexts.
        answer = " ".join(reference_contexts) if reference_contexts else ""
        return AgentResponse(answer=answer, contexts=reference_contexts)
