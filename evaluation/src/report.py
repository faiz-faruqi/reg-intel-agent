"""
report.py
---------
Generates the Model Risk Assessment (MRA) report - the artifact a model risk
committee or CRO actually consumes. Takes the EvaluationResult plus the control
mappings and produces a structured Markdown document.

The report is intentionally written as a reference-implementation artifact: it
assesses the assurance team's own system-under-test and documents methodology,
results, control coverage, and residual risk. It is not a substitute for an
institution's formal validation sign-off.
"""

from __future__ import annotations

import datetime as _dt
from typing import Dict, List

import yaml

from metrics import EvaluationResult, RAGAS_METRICS


# Architectural activities the system-under-test is known to implement.
# In live use, confirm these against the actual deployed system before relying
# on them as evidence.
OBSERVED_ACTIVITIES = {
    "human_in_the_loop_gate": True,
    "append_only_audit_log": True,
    "guardrails": True,
}


def _fmt(v) -> str:
    return f"{v:.3f}" if isinstance(v, float) else "n/a"


def _threshold(rule: str):
    return float(rule[2:]) if rule.startswith(">=") else None


def _metric_status(agg_value, per_item_values: list, rule: str) -> tuple[str, str]:
    """
    Returns (status, observed_text). A control is flagged ATTENTION if the
    aggregate misses the threshold OR a material share (>=15%) of individual
    items fall below it - so the framework surfaces localized weak spots that
    an aggregate would otherwise hide.
    """
    if agg_value is None or not per_item_values:
        return "NOT MEASURED", "n/a"
    thr = _threshold(rule)
    if thr is None:
        return "REVIEW", _fmt(agg_value)
    below = [v for v in per_item_values if v < thr]
    share_below = len(below) / len(per_item_values)
    observed = f"{agg_value:.3f} agg · {len(below)}/{len(per_item_values)} below {thr:g}"
    if agg_value < thr or share_below >= 0.15:
        return "ATTENTION", observed
    return "PASS", observed


def _pass_metric_simple(value, rule: str) -> str:
    if value is None:
        return "NOT MEASURED"
    if rule.startswith(">="):
        return "PASS" if value >= float(rule[2:]) else "ATTENTION"
    return "REVIEW"


def _pass_activity(key: str, rule: str) -> str:
    if rule == "present":
        return "PASS" if OBSERVED_ACTIVITIES.get(key) else "ATTENTION"
    return "REVIEW"


def _load_controls(mappings_path: str) -> list:
    with open(mappings_path) as f:
        return yaml.safe_load(f)["controls"]


def _residual_risk(status_counts: Dict[str, int]) -> str:
    attention = status_counts.get("ATTENTION", 0) + status_counts.get("NOT MEASURED", 0)
    if attention == 0:
        return "LOW"
    if attention <= 3:
        return "MODERATE"
    return "ELEVATED"


def generate_report(
    result: EvaluationResult,
    mappings_path: str,
    system_name: str = "Regulatory Intelligence Agent",
    intended_use: str = (
        "Answer questions about published AI governance and financial-services "
        "model-risk regulatory guidance, with citations to source material and a "
        "human approval gate before any action is taken."
    ),
) -> str:
    controls = _load_controls(mappings_path)
    agg = result.aggregate()
    today = _dt.date.today().isoformat()

    # Collect per-item metric values across answerable items.
    per_item_metric: Dict[str, list] = {m: [] for m in RAGAS_METRICS}
    for it in result.items:
        for m in RAGAS_METRICS:
            if m in it.scores and it.scores[m] is not None:
                per_item_metric[m].append(it.scores[m])

    # ---- Control assessment table ----
    control_rows: List[str] = []
    status_counts: Dict[str, int] = {}
    for c in controls:
        src = c["evidence_source"]
        if src.startswith("metric:"):
            metric = src.split(":", 1)[1]
            if metric == "refusal_correctness":
                value = agg.get("refusal_correctness")
                status = _pass_metric_simple(value, c.get("pass_rule", ""))
                observed = _fmt(value)
            else:
                value = agg.get(metric)
                status, observed = _metric_status(
                    value, per_item_metric.get(metric, []), c.get("pass_rule", "")
                )
        else:  # activity
            key = src.split(":", 1)[1]
            status = _pass_activity(key, c.get("pass_rule", ""))
            observed = "present" if OBSERVED_ACTIVITIES.get(key) else "absent"
        status_counts[status] = status_counts.get(status, 0) + 1
        control_rows.append(
            f"| {c['id']} | {c['name']} | {observed} | {status} | "
            f"{c['nist_ai_rmf']} | {c['osfi_e23']} |"
        )

    residual = _residual_risk(status_counts)

    # ---- Per-item results table ----
    _label = {
        "faithfulness": "faith",
        "answer_relevancy": "relevance",
        "context_precision": "precision",
        "context_recall": "recall",
    }
    item_rows: List[str] = []
    for it in result.items:
        if it.expected_behaviour == "out_of_scope":
            r = "correct refusal" if it.refusal_correct else "FAILED to refuse"
            item_rows.append(f"| {it.id} | {it.category} | out-of-scope | {r} |")
        else:
            s = it.scores
            cell = ", ".join(
                f"{_label[m]}={_fmt(s.get(m))}" for m in RAGAS_METRICS if m in s
            ) or "n/a"
            item_rows.append(f"| {it.id} | {it.category} | answerable | {cell} |")

    # ---- Recommendations ----
    recs: List[str] = []
    for c in controls:
        src = c["evidence_source"]
        if src.startswith("metric:"):
            metric = src.split(":", 1)[1]
            if metric == "refusal_correctness":
                continue
            status, _obs = _metric_status(
                agg.get(metric), per_item_metric.get(metric, []), c.get("pass_rule", "")
            )
            if status == "ATTENTION":
                recs.append(
                    f"- **{c['id']} {c['name']}**: one or more items fell below the "
                    f"{c['pass_rule']} threshold. Review the affected items in section 4.1, "
                    f"investigate retrieval quality and grounding for those queries, and "
                    f"re-test before relying on this control as evidence."
                )
    if not recs:
        recs.append("- All measured controls met their thresholds in this run. "
                    "Expand the golden dataset and add the Phase 2 adversarial suite "
                    "to strengthen the evidence base.")

    # ---- Assemble ----
    md = f"""# Model Risk Assessment

**System under assessment:** {system_name}
**Assessment date:** {today}
**Evaluation mode:** {result.mode}  |  **Model under test:** {result.model_label}
**Framework:** Enterprise AI Assurance Framework v1
**Overall residual risk:** {residual}

> This is a reference-implementation assurance report. It documents automated
> evaluation of the system's own outputs and its architectural controls. It is
> not a formal regulatory validation sign-off and should be reviewed by a
> qualified model-risk function before use as institutional evidence.

---

## 1. System Identification
- **Name:** {system_name}
- **Type:** Retrieval-augmented, multi-agent decision-support system
- **Knowledge source:** Curated corpus of published regulatory and governance guidance
- **Generation model:** {result.model_label}

## 2. Intended Use and Scope
{intended_use}

Out-of-scope use (strategic, financial, or legal decisions, or anything not
grounded in the knowledge source) is expected to be declined by the system.

## 3. Assessment Methodology
The system was evaluated against a golden dataset of curated questions with
expert-authored ground-truth answers and reference contexts. Answerable items
were scored on grounded-generation and retrieval quality; out-of-scope items
were scored on refusal correctness. Architectural controls (human oversight,
audit logging, guardrails) were assessed as observed activities. Quantitative
metrics are computed with RAGAS in live mode; this report was produced in
**{result.mode}** mode.

## 4. Evaluation Results (Aggregate)

| Metric | Score |
|---|---|
| Faithfulness (groundedness) | {_fmt(agg.get('faithfulness'))} |
| Answer relevancy | {_fmt(agg.get('answer_relevancy'))} |
| Context precision | {_fmt(agg.get('context_precision'))} |
| Context recall | {_fmt(agg.get('context_recall'))} |
| Refusal correctness | {_fmt(agg.get('refusal_correctness'))} |

### 4.1 Per-Item Results

| ID | Category | Type | Result |
|---|---|---|---|
{chr(10).join(item_rows)}

## 5. Control Assessment and Regulatory Mapping

| Control | Name | Observed | Status | NIST AI RMF | OSFI E-23 |
|---|---|---|---|---|---|
{chr(10).join(control_rows)}

Status legend: PASS (met threshold) · ATTENTION (below threshold, investigate) ·
NOT MEASURED (no data this run) · REVIEW (manual review required).

## 6. Residual Risk Assessment
Overall residual risk for the assessed scope is rated **{residual}**, based on {status_counts.get('PASS', 0)} control(s) passing, {status_counts.get('ATTENTION', 0)} requiring attention, and {status_counts.get('NOT MEASURED', 0)} not measured in this run. Residual risk should be re-evaluated against the institution's defined risk appetite and any third-party model-risk considerations.

## 7. Recommendations
{chr(10).join(recs)}

## 8. Appendix - Framework Coverage Notes
- v1 maps controls to **NIST AI RMF** and **OSFI E-23**.
- **ISO/IEC 42001** and **EU AI Act** mappings are scoped for Phase 2.
- The **adversarial / red-team suite** (prompt injection, jailbreak, PII
  leakage, hallucination-under-pressure) is scoped for Phase 2 and will extend
  Control CTL-08 and add new robustness controls.

---
*Generated by the Enterprise AI Assurance Framework. Methodology and code:
reference implementation by CloudKraft Consulting.*
"""
    return md
