"""Web search tool. Uses DuckDuckGo's HTML backend via the `duckduckgo-search`
package — no API key needed, which matters for a project other people will
try to actually run. Swap this for a paid search API (Tavily, Brave, Bing) if
you need higher reliability at scale; the return shape is what matters to the
rest of the app, not the provider.
"""

from __future__ import annotations

from ddgs import DDGS

from ..config import settings


def web_search(query: str, max_results: int | None = None) -> list[dict]:
    """Returns a list of {title, url, snippet} dicts. Raises on network
    failure — callers decide whether that's fatal or just means fewer
    resources for this concept, they should not silently swallow it here."""
    n = max_results or settings.max_resources_per_concept
    with DDGS(timeout=settings.tool_timeout_seconds) as ddgs:
        results = ddgs.text(query, max_results=n)
    return [
        {
            "title": r.get("title", ""),
            "url": r.get("href", ""),
            "snippet": r.get("body", ""),
        }
        for r in results
    ]
