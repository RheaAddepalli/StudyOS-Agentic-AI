"""Research paper search via the public arXiv API (no key required).

Only useful for topics with a research-depth component — the calling node
decides whether to invoke this based on LearningGoal.wants_research_depth or
a concept's learning_type == "research", it is not called unconditionally.
"""

from __future__ import annotations

from xml.etree import ElementTree

import httpx

from ..config import settings

_ARXIV_API = "http://export.arxiv.org/api/query"
_NS = {"atom": "http://www.w3.org/2005/Atom"}


def arxiv_search(query: str, max_results: int | None = None) -> list[dict]:
    """Returns [{title, url, summary, authors, published}]."""
    n = max_results or settings.max_resources_per_concept
    params = {
        "search_query": f"all:{query}",
        "start": 0,
        "max_results": n,
        "sortBy": "relevance",
    }
    resp = httpx.get(_ARXIV_API, params=params, timeout=settings.tool_timeout_seconds)
    resp.raise_for_status()
    root = ElementTree.fromstring(resp.text)

    out = []
    for entry in root.findall("atom:entry", _NS):
        title = (entry.findtext("atom:title", default="", namespaces=_NS) or "").strip()
        summary = (entry.findtext("atom:summary", default="", namespaces=_NS) or "").strip()
        published = entry.findtext("atom:published", default="", namespaces=_NS) or ""
        link = ""
        for l in entry.findall("atom:link", _NS):
            if l.get("type") == "text/html" or l.get("rel") == "alternate":
                link = l.get("href", "")
                break
        authors = [
            a.findtext("atom:name", default="", namespaces=_NS)
            for a in entry.findall("atom:author", _NS)
        ]
        out.append(
            {
                "title": title,
                "url": link,
                "summary": summary,
                "authors": authors,
                "published": published,
            }
        )
    return out
