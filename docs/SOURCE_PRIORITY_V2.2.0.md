# Source Priority V2.2.0

1. Truth Social Official Timeline — configured official profile URL, public same-host JSON timeline, 72-hour filter.
2. Existing licensed Truth API — retained unchanged.
3. Existing manual Truth JSON import — retained unchanged.
4. Existing Truth search index — retained unchanged as discovery/fallback.
5. Reuters/AP/Bloomberg verification via existing feeds.
6. Google News RSS.
7. NewsAPI/GNews.

The new collector does not delete, rename, or replace existing collectors. It fails independently and records a source status.
