#!/usr/bin/env python3
"""
Eval harness: runs 10 fixed compliance questions through the Knowledge + Analysis
pipeline and scores faithfulness (citation present AND correct source cited).

Prerequisites:
  - Documents ingested: PYTHONPATH=. .venv/bin/python -m src.ingest
  - Env vars set: OPENROUTER_API_KEY, DATABASE_URL (or .env file)

Usage:
  PYTHONPATH=. .venv/bin/python scripts/eval.py
"""

import sys
import time
from dataclasses import dataclass


@dataclass
class EvalCase:
    question: str
    expected_sources: list[str]  # case-insensitive substrings expected in citations


@dataclass
class EvalResult:
    case: EvalCase
    cited: bool
    source_hit: bool
    length_ok: bool
    citations: list[str]
    response_length: int
    error: str | None = None

    @property
    def faithful(self) -> bool:
        return self.cited and self.source_hit

    @property
    def status(self) -> str:
        if self.error:
            return "ERROR"
        if self.faithful:
            return "PASS"
        if self.cited and not self.source_hit:
            return "WRONG SRC"
        return "FAIL"


EVAL_CASES = [
    EvalCase(
        question="What are the GDPR data minimisation requirements?",
        expected_sources=["GDPR"],
    ),
    EvalCase(
        question="What are the data subject rights under GDPR Article 17?",
        expected_sources=["GDPR"],
    ),
    EvalCase(
        question="What does ISO 27001 require for privileged access management?",
        expected_sources=["ISO"],
    ),
    EvalCase(
        question="What cryptography standards does ISO 27001 Annex A.8 mandate?",
        expected_sources=["ISO"],
    ),
    EvalCase(
        question="What are the Basel III minimum capital adequacy requirements?",
        expected_sources=["Basel"],
    ),
    EvalCase(
        question="What are the Basel III liquidity coverage ratio and net stable funding ratio requirements?",
        expected_sources=["Basel"],
    ),
    EvalCase(
        question="What does OSFI E-23 require for model validation?",
        expected_sources=["E-23"],
    ),
    EvalCase(
        question="How does OSFI E-23 define model risk?",
        expected_sources=["E-23"],
    ),
    EvalCase(
        question="What does OSFI B-20 require for residential mortgage stress testing?",
        expected_sources=["B-20"],
    ),
    EvalCase(
        question="What are the PIPEDA consent requirements for collecting personal information?",
        expected_sources=["PIPEDA"],
    ),
]


def _source_hit(citations: list[str], expected: list[str]) -> bool:
    text = " ".join(citations).lower()
    return any(kw.lower() in text for kw in expected)


def run_case(case: EvalCase, top_k: int = 5) -> EvalResult:
    from src.graph import graph

    initial_state: dict = {
        "question": case.question,
        "top_k": top_k,
        "retrieved_chunks": [],
        "draft_response": "",
        "citations": [],
        "is_cited": False,
        "next": "",
    }
    try:
        result = graph.invoke(initial_state)
        citations = result.get("citations", [])
        response = result.get("draft_response", "")
        return EvalResult(
            case=case,
            cited=result.get("is_cited", False),
            source_hit=_source_hit(citations, case.expected_sources),
            length_ok=len(response) >= 100,
            citations=citations,
            response_length=len(response),
        )
    except Exception as exc:
        return EvalResult(
            case=case,
            cited=False,
            source_hit=False,
            length_ok=False,
            citations=[],
            response_length=0,
            error=str(exc)[:120],
        )


def main() -> None:
    from src.db import document_count

    print("\nEval Harness — Regulatory Intelligence Agent")
    print("═" * 78)

    try:
        count = document_count()
    except Exception as exc:
        print(f"\n[ERROR] Cannot connect to database: {exc}")
        print("Check DATABASE_URL and run: PYTHONPATH=. .venv/bin/python -m src.ingest")
        sys.exit(1)

    if count == 0:
        print("\n[ERROR] Documents table is empty — run ingest first:")
        print("  PYTHONPATH=. .venv/bin/python -m src.ingest")
        sys.exit(1)

    print(f"\n{count} document chunk(s) in store. Running {len(EVAL_CASES)} eval cases...\n")

    col_q = 44
    print(f" {'#':>2}  {'Question':<{col_q}}  {'Cited':^6}  {'Source':^7}  {'Len':>5}  Status")
    print("─" * 78)

    results: list[EvalResult] = []
    for i, case in enumerate(EVAL_CASES, 1):
        q_short = (case.question[:col_q - 1] + "…") if len(case.question) > col_q else case.question
        print(f" {i:>2}  {q_short:<{col_q}}  ", end="", flush=True)

        result = run_case(case)
        results.append(result)

        c = "✓" if result.cited else "✗"
        s = "✓" if result.source_hit else "✗"
        print(f"  {c}     {s}      {result.response_length:>5}  {result.status}")

        if i < len(EVAL_CASES):
            time.sleep(1)  # avoid OpenRouter free-tier rate limits

    n = len(results)
    n_cited = sum(1 for r in results if r.cited)
    n_source = sum(1 for r in results if r.source_hit)
    n_faithful = sum(1 for r in results if r.faithful)
    n_errors = sum(1 for r in results if r.error)

    print("═" * 78)
    def pct(num: int) -> str:
        return f"{100 * num // n}%" if n else "0%"

    print(f"  Cited:          {n_cited}/{n} ({pct(n_cited)})")
    print(f"  Source hits:    {n_source}/{n} ({pct(n_source)})")
    print(f"  Faithful:       {n_faithful}/{n} ({pct(n_faithful)})  <- cited AND correct source")
    if n_errors:
        print(f"  Errors:         {n_errors}/{n}")
    print("═" * 78)

    failures = [r for r in results if not r.faithful]
    if failures:
        print("\nFailed / partial cases:")
        for r in failures:
            print(f"\n  Q: {r.case.question}")
            if r.error:
                print(f"     Error: {r.error}")
            elif not r.cited:
                print("     No citations — check documents are ingested and top_k > 0")
            else:
                print(f"     Citations found: {r.citations}")
                print(f"     Expected source keyword(s): {r.case.expected_sources}")

    print()
    if n_faithful == n:
        print("  All cases faithful — pipeline is demo-ready.\n")
    elif n_faithful >= n * 0.8:
        print(f"  {n_faithful}/{n} faithful — good enough for demo.\n")
    else:
        print(f"  {n_faithful}/{n} faithful — re-check ingest or model quality.\n")


if __name__ == "__main__":
    main()
