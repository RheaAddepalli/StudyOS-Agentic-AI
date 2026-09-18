"""GitHub repository search via the REST API. Works unauthenticated (60
requests/hour); set GITHUB_TOKEN in .env to raise that to 5000/hour.
"""

from __future__ import annotations

import httpx

from ..config import settings

_API = "https://api.github.com/search/repositories"


def github_search(query: str, max_results: int | None = None) -> list[dict]:
    """Returns [{title, url, description, stars, language}], sorted by stars
    so the evaluation node sees the most-maintained implementations first."""
    n = max_results or settings.max_resources_per_concept
    headers = {"Accept": "application/vnd.github+json"}
    if settings.github_token:
        headers["Authorization"] = f"Bearer {settings.github_token}"

    params = {"q": query, "sort": "stars", "order": "desc", "per_page": n}
    resp = httpx.get(_API, params=params, headers=headers, timeout=settings.tool_timeout_seconds)
    resp.raise_for_status()
    items = resp.json().get("items", [])

    return [
        {
            "title": item.get("full_name", ""),
            "url": item.get("html_url", ""),
            "description": item.get("description") or "",
            "stars": item.get("stargazers_count", 0),
            "language": item.get("language") or "",
        }
        for item in items
    ]
