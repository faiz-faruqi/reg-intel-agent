"""Jira Cloud issue creation tool — alternative ticket backend to GitHub."""

import base64
import logging

import requests

from src.config import settings

logger = logging.getLogger(__name__)


def create_jira_issue(
    title: str,
    body: str,
    labels: list[str] | None = None,
) -> dict:
    """
    Create a Jira Cloud issue via REST API v3.
    Returns {"key": str, "url": str, "title": str}.
    Raises ValueError if credentials are missing, requests.HTTPError on API failure.
    """
    missing = [
        name for name, val in [
            ("JIRA_URL", settings.JIRA_URL),
            ("JIRA_EMAIL", settings.JIRA_EMAIL),
            ("JIRA_API_TOKEN", settings.JIRA_API_TOKEN),
            ("JIRA_PROJECT_KEY", settings.JIRA_PROJECT_KEY),
        ] if not val
    ]
    if missing:
        raise ValueError(f"Jira credentials not configured: {', '.join(missing)}")

    token = base64.b64encode(
        f"{settings.JIRA_EMAIL}:{settings.JIRA_API_TOKEN}".encode()
    ).decode()

    headers = {
        "Authorization": f"Basic {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    # Jira API v3 requires Atlassian Document Format (ADF) for description
    payload: dict = {
        "fields": {
            "project": {"key": settings.JIRA_PROJECT_KEY},
            "summary": title,
            "description": {
                "type": "doc",
                "version": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": body}],
                    }
                ],
            },
            "issuetype": {"name": "Task"},
        }
    }
    if labels:
        payload["fields"]["labels"] = labels

    api_url = f"{settings.JIRA_URL.rstrip('/')}/rest/api/3/issue"
    resp = requests.post(api_url, json=payload, headers=headers, timeout=15)
    resp.raise_for_status()

    data = resp.json()
    key = data["key"]
    url = f"{settings.JIRA_URL.rstrip('/')}/browse/{key}"
    logger.info("Jira issue created: %s %s", key, url)
    return {"key": key, "url": url, "title": title}
