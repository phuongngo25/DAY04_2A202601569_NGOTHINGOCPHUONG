from __future__ import annotations

import time
from typing import Any

import requests

from tools._shared import TIMEOUT, domain, err


HN_ITEM_URL = "https://news.ycombinator.com/item?id={object_id}"

TIMEFRAME_SECONDS = {
    "day": 86400,
    "week": 7 * 86400,
    "month": 30 * 86400,
    "year": 365 * 86400,
}


def _numeric_filters(timeframe: str, min_points: int) -> str:
    filters: list[str] = []
    window = TIMEFRAME_SECONDS.get((timeframe or "all").strip().lower())
    if window:
        filters.append(f"created_at_i>{int(time.time()) - window}")
    if min_points and int(min_points) > 0:
        filters.append(f"points>={int(min_points)}")
    return ",".join(filters)


def _summary(hit: dict[str, Any]) -> str:
    story_text = (hit.get("story_text") or hit.get("comment_text") or "").strip()
    stats = f"{hit.get('points') or 0} points, {hit.get('num_comments') or 0} comments by {hit.get('author') or 'unknown'}"
    if not story_text:
        return stats
    if len(story_text) > 400:
        story_text = story_text[:397] + "..."
    return f"{stats}. {story_text}"


def search_hackernews(
    query: str = "",
    sort_by: str = "relevance",
    timeframe: str = "all",
    min_points: int = 0,
    limit: int = 5,
) -> dict[str, Any]:
    try:
        if not (query or "").strip():
            raise ValueError("query is required")

        sort_by = (sort_by or "relevance").strip().lower()
        endpoint = "search_by_date" if sort_by == "recent" else "search"
        params: dict[str, Any] = {
            "query": query,
            "tags": "story",
            "hitsPerPage": max(1, int(limit or 5)),
        }
        numeric_filters = _numeric_filters(timeframe, min_points)
        if numeric_filters:
            params["numericFilters"] = numeric_filters

        response = requests.get(
            f"https://hn.algolia.com/api/v1/{endpoint}",
            params=params,
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()

        items: list[dict[str, Any]] = []
        for hit in data.get("hits", []):
            permalink = HN_ITEM_URL.format(object_id=hit.get("objectID"))
            url = hit.get("url") or permalink
            items.append({
                "title": hit.get("title") or hit.get("story_title"),
                "url": url,
                "source": domain(url) or "news.ycombinator.com",
                "summary": _summary(hit),
                "points": hit.get("points"),
                "comments": hit.get("num_comments"),
                "author": hit.get("author"),
                "created_at": hit.get("created_at"),
                "discussion_url": permalink,
            })

        return {
            "tool": "search_hackernews",
            "query": query,
            "sort_by": sort_by,
            "timeframe": (timeframe or "all").strip().lower(),
            "min_points": int(min_points or 0),
            "total_results": data.get("nbHits"),
            "items": items,
            "freshness": "live_hackernews_index",
        }
    except Exception as exc:
        return err("search_hackernews", exc)
