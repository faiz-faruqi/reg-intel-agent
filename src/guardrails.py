"""
Application-level content guardrails — mirrors the Bedrock Guardrails API contract.

In production (AWS path) these checks are replaced by a Bedrock Guardrail resource
configured with the same denied-topic and PII policies. The function signatures are
intentionally identical so the swap is a one-line config change.
"""

import re
from typing import NamedTuple


class GuardrailResult(NamedTuple):
    allowed: bool
    reason: str | None


# ---------------------------------------------------------------------------
# Denied topics — questions the system refuses to engage with
# ---------------------------------------------------------------------------

_DENIED_TOPICS: list[str] = [
    "how to hack",
    "bypass security controls",
    "exploit vulnerability",
    "evade compliance",
    "launder money",
    "avoid detection",
    "circumvent regulation",
]

# ---------------------------------------------------------------------------
# PII patterns — flag if the *response* leaks personal data
# ---------------------------------------------------------------------------

_PII_PATTERNS: list[tuple[str, str]] = [
    (r"\b\d{3}-\d{2}-\d{4}\b", "Social Security Number"),
    (r"\b(?:\d{4}[\s\-]){3}\d{4}\b", "credit card number"),
    (r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b", "email address"),
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def check_input(text: str) -> GuardrailResult:
    """Deny questions that match a denied topic."""
    lower = text.lower()
    for topic in _DENIED_TOPICS:
        if topic in lower:
            return GuardrailResult(allowed=False, reason=f"Denied topic: '{topic}'")
    return GuardrailResult(allowed=True, reason=None)


def check_output(text: str) -> GuardrailResult:
    """Block responses that contain PII patterns."""
    for pattern, label in _PII_PATTERNS:
        if re.search(pattern, text):
            return GuardrailResult(allowed=False, reason=f"PII detected in output: {label}")
    return GuardrailResult(allowed=True, reason=None)
