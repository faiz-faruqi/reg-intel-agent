"""
metrics.py
----------
Scoring layer. Isolated so the RAGAS/LLM dependencies are only imported in
live mode. Returns a uniform results structure consumed by report.py.

Metrics (RAGAS, live mode):
  faithfulness        - answer is grounded in retrieved context
  answer_relevancy    - answer addresses the question
  context_precision   - retrieved context is relevant (uses reference)
  context_recall      - relevant context was retrieved (uses reference)

refusal_correctness is computed directly (not via RAGAS): for out_of_scope
items, the system should decline; for answerable items it should not.

LIVE MODE TODO
  RAGAS evolves quickly. This integration targets ragas==0.2.x (see
  requirements.txt). If you upgrade RAGAS, verify the metric imports and the
  evaluate() signature against that version. Keep this module as the single
  place that needs adjusting.
"""

from __future__ import annotations

import os
import random
from dataclasses import dataclass, field
from typing import Dict, List

# Keys for the per-RAGAS-item scores we track.
RAGAS_METRICS = ["faithfulness", "answer_relevancy", "context_precision", "context_recall"]


@dataclass
class ItemResult:
    id: str
    category: str
    expected_behaviour: str
    question: str
    answer: str
    scores: Dict[str, float] = field(default_factory=dict)
    refused: bool = False
    refusal_correct: bool | None = None


@dataclass
class EvaluationResult:
    mode: str
    model_label: str
    items: List[ItemResult]

    def aggregate(self) -> Dict[str, float]:
        agg: Dict[str, List[float]] = {m: [] for m in RAGAS_METRICS}
        refusal_flags: List[float] = []
        for it in self.items:
            for m in RAGAS_METRICS:
                if m in it.scores and it.scores[m] is not None:
                    agg[m].append(it.scores[m])
            if it.refusal_correct is not None:
                refusal_flags.append(1.0 if it.refusal_correct else 0.0)
        out = {m: (sum(v) / len(v) if v else None) for m, v in agg.items()}
        out["refusal_correctness"] = (
            sum(refusal_flags) / len(refusal_flags) if refusal_flags else None
        )
        return out


# ---------------------------------------------------------------------------
# Refusal detection (shared by both modes)
# ---------------------------------------------------------------------------
_REFUSAL_MARKERS = [
    "cannot provide", "outside the scope", "outside its scope", "cannot answer",
    "unable to answer", "i cannot", "i can't", "not within", "falls outside",
    "do not have", "don't have", "cannot speculate",
]


def _looks_like_refusal(answer: str) -> bool:
    a = (answer or "").lower()
    return any(marker in a for marker in _REFUSAL_MARKERS)


def _score_refusal(item, answer: str) -> tuple[bool, bool]:
    refused = _looks_like_refusal(answer)
    if item["expected_behaviour"] == "out_of_scope":
        correct = refused
    else:
        correct = not refused
    return refused, correct


# ---------------------------------------------------------------------------
# MOCK scoring
# ---------------------------------------------------------------------------
def evaluate_mock(dataset_items: list, responses: list, model_label: str = "mock-model") -> EvaluationResult:
    rng = random.Random(42)  # deterministic sample
    results: List[ItemResult] = []

    for item, resp in zip(dataset_items, responses):
        refused, refusal_correct = _score_refusal(item, resp.answer)
        scores: Dict[str, float] = {}

        if item["expected_behaviour"] == "answerable":
            # Heuristic: if the mock answer dropped or padded context, score lower.
            answered_with_full_context = len(resp.contexts) >= len(item.get("reference_contexts", []))
            unsupported = "not stated in the source" in resp.answer or "could not be confirmed" in resp.answer

            def band(hi=True):
                return round(rng.uniform(0.86, 0.97), 3) if hi else round(rng.uniform(0.55, 0.74), 3)

            scores["faithfulness"] = band(hi=not unsupported)
            scores["answer_relevancy"] = band(hi=True)
            scores["context_precision"] = band(hi=answered_with_full_context)
            scores["context_recall"] = band(hi=answered_with_full_context)

        results.append(ItemResult(
            id=item["id"], category=item["category"],
            expected_behaviour=item["expected_behaviour"],
            question=item["question"], answer=resp.answer,
            scores=scores, refused=refused, refusal_correct=refusal_correct,
        ))

    return EvaluationResult(mode="mock", model_label=model_label, items=results)


# ---------------------------------------------------------------------------
# LIVE scoring (RAGAS)
# ---------------------------------------------------------------------------
def evaluate_live(dataset_items: list, responses: list, model_label: str) -> EvaluationResult:
    from ragas import evaluate, EvaluationDataset
    from ragas.metrics import (
        Faithfulness,
        ResponseRelevancy,
        LLMContextPrecisionWithReference,
        LLMContextRecall,
    )
    from ragas.llms import LangchainLLMWrapper
    from ragas.embeddings import LangchainEmbeddingsWrapper
    from langchain_openai import ChatOpenAI, OpenAIEmbeddings

    # Judge LLM via OpenRouter; embeddings via OpenAI (text-embedding-3-small).
    judge_llm = LangchainLLMWrapper(ChatOpenAI(
        model=os.getenv("JUDGE_MODEL", "openai/gpt-4o-mini"),
        base_url=os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
        api_key=os.getenv("OPENROUTER_API_KEY"),
        temperature=0,
    ))
    judge_emb = LangchainEmbeddingsWrapper(OpenAIEmbeddings(
        model=os.getenv("EMBED_MODEL", "text-embedding-3-small"),
        api_key=os.getenv("OPENROUTER_API_KEY"),
        base_url=os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
    ))

    # Build the RAGAS dataset only from answerable items (refusal scored separately).
    answerable = [(it, r) for it, r in zip(dataset_items, responses)
                  if it["expected_behaviour"] == "answerable"]

    samples = []
    for it, r in answerable:
        samples.append({
            "user_input": it["question"],
            "response": r.answer,
            "retrieved_contexts": r.contexts or [""],
            "reference": it["ground_truth"],
            "reference_contexts": it.get("reference_contexts", []),
        })

    metrics = [
        Faithfulness(llm=judge_llm),
        ResponseRelevancy(llm=judge_llm, embeddings=judge_emb),
        LLMContextPrecisionWithReference(llm=judge_llm),
        LLMContextRecall(llm=judge_llm),
    ]

    ragas_scores = {}
    if samples:
        eval_ds = EvaluationDataset.from_list(samples)
        result = evaluate(dataset=eval_ds, metrics=metrics, llm=judge_llm, embeddings=judge_emb)
        df = result.to_pandas()
        # Map RAGAS column names to our internal metric keys.
        colmap = {
            "faithfulness": "faithfulness",
            "answer_relevancy": "answer_relevancy",
            "response_relevancy": "answer_relevancy",
            "llm_context_precision_with_reference": "context_precision",
            "context_precision": "context_precision",
            "context_recall": "context_recall",
            "llm_context_recall": "context_recall",
        }
        for idx, (it, _r) in enumerate(answerable):
            row = df.iloc[idx]
            per_item = {}
            for col, key in colmap.items():
                if col in df.columns:
                    val = row[col]
                    if val == val:  # not NaN
                        per_item[key] = float(val)
            ragas_scores[it["id"]] = per_item

    results: List[ItemResult] = []
    for it, r in zip(dataset_items, responses):
        refused, refusal_correct = _score_refusal(it, r.answer)
        results.append(ItemResult(
            id=it["id"], category=it["category"],
            expected_behaviour=it["expected_behaviour"],
            question=it["question"], answer=r.answer,
            scores=ragas_scores.get(it["id"], {}),
            refused=refused, refusal_correct=refusal_correct,
        ))

    return EvaluationResult(mode="live", model_label=model_label, items=results)
