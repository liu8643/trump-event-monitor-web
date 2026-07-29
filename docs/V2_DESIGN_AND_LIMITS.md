# V2 design and limits
- Truth full text: supported for licensed API/manual import. Search-index results remain snippets and are labeled, not falsely promoted to full text.
- Reuters/Bloomberg: the system summarizes text legally supplied by APIs/RSS/licensed feeds; it does not bypass paywalls or copy full articles.
- AI classification: deterministic rule engine is always available; an optional OpenAI-compatible endpoint can be configured with AI_API_URL/AI_API_KEY/AI_MODEL.
- Taiwan candidates: event-to-sector-to-stock mapping; WATCH only until live price/liquidity/portfolio gates are connected.
- GTC WatchList: generated as review-required JSON/CSV; no silent write into an external GTC database.
- 5-minute automation: browser auto-refresh works while the page is open; GitHub scheduled workflow is best effort and may be delayed by GitHub.
