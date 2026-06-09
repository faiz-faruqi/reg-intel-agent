"""GitHub issue creation tool — the one MCP-style write action for Phase 2."""

import logging

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from src.config import settings

logger = logging.getLogger(__name__)

_GITHUB_API = "https://api.github.com"


def _session() -> requests.Session:
    s = requests.Session()
    retry = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
    s.mount("https://", HTTPAdapter(max_retries=retry))
    return s


def create_github_issue(
    title: str,
    body: str,
    labels: list[str] | None = None,
) -> dict:
    """
    Create a GitHub issue in the configured repo.
    Returns {"number": int, "url": str, "title": str}.
    Raises ValueError if credentials are missing, requests.HTTPError on API failure.
    """
    if not settings.GITHUB_TOKEN:
        raise ValueError("GITHUB_TOKEN is not set — cannot create GitHub issue")
    if not settings.GITHUB_REPO:
        raise ValueError("GITHUB_REPO is not set — cannot create GitHub issue")

    url = f"{_GITHUB_API}/repos/{settings.GITHUB_REPO}/issues"
    headers = {
        "Authorization": f"token {settings.GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
    }
    payload: dict = {"title": title, "body": body}
    if labels:
        payload["labels"] = labels

    resp = _session().post(url, json=payload, headers=headers, timeout=15)
    resp.raise_for_status()

    data = resp.json()
    logger.info("GitHub issue created: #%d %s", data["number"], data["html_url"])
    return {"number": data["number"], "url": data["html_url"], "title": title}
