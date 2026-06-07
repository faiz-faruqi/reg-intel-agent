"""
Quick local test: try free OpenRouter models and verify citation format
and JSON proposal output still hold up.

Run from repo root:
    PYTHONPATH=. .venv/bin/python scripts/test_free_model.py
"""

import json
import os
import sys

CANDIDATES = [
    "meta-llama/llama-3.3-70b-instruct:free",
    "google/gemini-2.0-flash-exp:free",
    "mistralai/mistral-7b-instruct:free",
]

FREE_MODEL = os.environ.get("OPENROUTER_MODEL_ID", CANDIDATES[0])
os.environ["OPENROUTER_MODEL_ID"] = FREE_MODEL

from dotenv import load_dotenv
load_dotenv()
os.environ["OPENROUTER_MODEL_ID"] = FREE_MODEL  # keep override after dotenv

from src.config import settings

print(f"Model under test : {settings.OPENROUTER_MODEL_ID}")
print(f"Embedding model  : {settings.EMBEDDING_MODEL}")
print("-" * 60)


def _make_chat(model_id: str = None):
    from langchain_openai import ChatOpenAI
    return ChatOpenAI(
        model=model_id or settings.OPENROUTER_MODEL_ID,
        api_key=settings.OPENROUTER_API_KEY,
        base_url="https://openrouter.ai/api/v1",
        temperature=0,
        max_tokens=4096,  # cap for free-tier providers
    )


def run_test(label: str, question: str) -> dict:
    from src.agents.knowledge_agent import knowledge_agent, _embeddings_model
    from src.agents.analysis_agent import analysis_agent, _chat_model
    import src.agents.analysis_agent as _aa

    _embeddings_model.cache_clear()
    # Patch chat model with max_tokens cap
    _aa._chat_model = _make_chat  # replace lru_cache fn with plain factory

    state: dict = {
        "question": question,
        "top_k": 5,
        "retrieved_chunks": [],
        "draft_response": "",
        "citations": [],
        "is_cited": False,
        "next": "",
    }

    print(f"\n[TEST] {label}")
    print(f"Q: {question}")

    state.update(knowledge_agent(state))
    print(f"  → retrieved {len(state['retrieved_chunks'])} chunks")

    state.update(analysis_agent(state))

    print(f"  → response length : {len(state['draft_response'])} chars")
    print(f"  → citations found : {len(state['citations'])}")
    print(f"  → is_cited        : {state['is_cited']}")

    print(f"\n  Response:\n{state['draft_response']}\n")
    if state["citations"]:
        for c in state["citations"]:
            print(f"  ✓ {c}")
    else:
        print("  ⚠  NO CITATIONS — model did not follow [N] format")

    return state


def run_action_test(state: dict) -> None:
    from src.agents.action_agent import action_agent
    import src.agents.action_agent as _act
    _act._chat_model = _make_chat  # replace with factory, not cached fn

    print("\n[TEST] Action Agent — JSON proposal")
    result = action_agent(state)
    raw = result.get("proposed_action", "{}")
    try:
        proposal = json.loads(raw)
        print(f"  → title  : {proposal.get('title', '—')}")
        print(f"  → labels : {proposal.get('labels', [])}")
        body_preview = (proposal.get("body", "") or "")[:120].replace("\n", " ")
        print(f"  → body   : {body_preview}…")
        print("  ✓ valid JSON")
    except json.JSONDecodeError:
        print(f"  ✗ INVALID JSON: {raw[:200]}")


if __name__ == "__main__":
    try:
        state1 = run_test(
            "Citation test — GDPR",
            "What are the GDPR data minimisation requirements?",
        )

        state2 = run_test(
            "Citation test — ISO 27001",
            "What does ISO 27001 require for access control?",
        )

        # Run action agent on whichever state has citations
        best = state1 if state1["is_cited"] else state2
        if best["is_cited"]:
            run_action_test(best)
        else:
            print("\n⚠  Skipping Action Agent test — no cited state to work from")

        print("\n" + "=" * 60)
        both_cited = state1["is_cited"] and state2["is_cited"]
        if both_cited:
            print("RESULT: PASS — citations present in both responses")
            print(f"Safe to set OPENROUTER_MODEL_ID={FREE_MODEL} in Railway")
        else:
            print("RESULT: PARTIAL — at least one response missing citations")
            print("Consider sticking with Claude Sonnet for reliable citation format")
        print("=" * 60)

    except Exception as exc:
        print(f"\nERROR: {exc}")
        sys.exit(1)
