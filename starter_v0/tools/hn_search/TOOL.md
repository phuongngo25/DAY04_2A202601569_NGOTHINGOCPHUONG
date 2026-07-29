---
name: hn_search
track: group
kind: live_api
provider: Hacker News (Algolia Search API)
requires_env: []
inputs: [query, sort_by, timeframe, min_points, limit]
outputs: [items]
side_effect: false
---
# hn_search

Searches Hacker News stories through the public Algolia index. No API key and no
account is required, so this tool is always available even when the paid research
APIs are rate-limited.

## When to use

- The user names Hacker News / HN / "trên HN" explicitly.
- The user asks what the **developer community** thinks about a technical topic,
  or asks for discussion threads / comment counts rather than news articles.
- The user asks for stories filtered by community traction ("trên 100 điểm",
  "bài được upvote nhiều nhất").

## When NOT to use

- General web news → use `lookup` with `topic=news`. HN is one community, not the web.
- Twitter/X posts or opinions → use `social_search`, or `timeline` for one account.
- The user already gave a concrete URL to read → use `fetch`.
- Academic papers → use `papers`.

## Argument conventions

| Argument | Type | Default | Convention |
|---|---|---|---|
| `query` | string | — | Required. Topic keywords only, no "on Hacker News" filler. |
| `sort_by` | `relevance` \| `recent` | `relevance` | "mới nhất", "gần đây", "hôm nay" → `recent`. "phổ biến", "nổi bật", "top" → `relevance` (Algolia ranks by popularity). |
| `timeframe` | `day` \| `week` \| `month` \| `year` \| `all` | `all` | Map the user's words: "hôm nay" → `day`, "tuần này" → `week`, "tháng này" → `month`. Only set it when the user restricts time; otherwise leave `all`. |
| `min_points` | integer | `0` | Only when the user states a traction threshold ("trên 100 điểm" → `100`). Never invent a threshold. |
| `limit` | integer | `5` | Take the number the user asks for ("5 bài" → `5`). |

## Output contract

Returns `items[]` with `title`, `url`, `source`, `summary`, plus HN-specific
`points`, `comments`, `author`, `created_at`, and `discussion_url` (the HN thread
permalink, which differs from `url` when the story links to an external site).
`items` is `[]` when nothing matches — that is a valid empty result, not an error.
Errors return `error` and `message` instead of `items`.

## Confirmation boundary

None. `hn_search` is read-only and has no side effect, so it never needs
confirmation before running. Only write/publish actions (`send`) do.
