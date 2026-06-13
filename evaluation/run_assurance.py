"""
run_assurance.py
----------------
Entry point for the Enterprise AI Assurance Framework.

Usage:
    python run_assurance.py                 # mock mode (default), writes sample report
    python run_assurance.py --mode live     # evaluate the live Regulatory Intelligence Agent
    python run_assurance.py --out report.md # custom output path

Mock mode needs only `pyyaml`. Live mode additionally needs the packages in
requirements.txt and a populated .env (see .env.example).
"""

from __future__ import annotations

import argparse
import json
import os
import sys

# Load .env from the evaluation/ directory if present (live mode needs API keys).
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
except ImportError:
    pass

# ragas 0.2.x has a hard import of ChatVertexAI from langchain_community, which
# was removed in langchain-community 0.3+. Stub it out — we use OpenRouter, not VertexAI.
try:
    import langchain_community.chat_models.vertexai  # noqa: F401
except (ImportError, ModuleNotFoundError):
    import types as _types
    _stub = _types.ModuleType("langchain_community.chat_models.vertexai")
    _stub.ChatVertexAI = type("ChatVertexAI", (), {})
    sys.modules["langchain_community.chat_models.vertexai"] = _stub

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from agent_client import AgentClient            # noqa: E402
from metrics import evaluate_mock, evaluate_live  # noqa: E402
from report import generate_report               # noqa: E402

ROOT = os.path.dirname(__file__)
DATASET_PATH = os.path.join(ROOT, "data", "golden_dataset.json")
MAPPINGS_PATH = os.path.join(ROOT, "mappings", "control_mappings.yaml")


def load_dataset(path: str) -> list:
    with open(path) as f:
        return json.load(f)["items"]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run an AI assurance evaluation.")
    parser.add_argument("--mode", choices=["mock", "live"], default="mock")
    parser.add_argument("--out", default=os.path.join(ROOT, "samples", "model_risk_assessment_sample.md"))
    parser.add_argument("--model-label", default=None,
                        help="Label for the model under test (e.g. 'OpenRouter/Gemma' or 'AWS Bedrock/Claude').")
    args = parser.parse_args()

    items = load_dataset(DATASET_PATH)
    client = AgentClient(mode=args.mode)

    model_label = args.model_label or (
        "mock-model" if args.mode == "mock" else os.getenv("AGENT_MODEL_LABEL", "system-under-test")
    )

    print(f"[assurance] mode={args.mode}  items={len(items)}  model={model_label}")

    responses = [
        client.query(
            it["question"],
            reference_contexts=it.get("reference_contexts"),
            expected_behaviour=it["expected_behaviour"],
        )
        for it in items
    ]

    if args.mode == "mock":
        result = evaluate_mock(items, responses, model_label=model_label)
    else:
        result = evaluate_live(items, responses, model_label=model_label)

    report_md = generate_report(result, MAPPINGS_PATH)

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as f:
        f.write(report_md)

    agg = result.aggregate()
    print("[assurance] aggregate scores:")
    for k, v in agg.items():
        print(f"            {k:22s} {v if v is None else round(v, 3)}")
    print(f"[assurance] report written to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
