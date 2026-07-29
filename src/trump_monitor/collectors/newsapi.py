from __future__ import annotations

from datetime import datetime, timezone
import os
import requests

from trump_monitor.collectors.base import SourceAdapter, SourceError
from trump_monitor.models import RawItem


class NewsApiAdapter(SourceAdapter):
    name = "newsapi"

    def __init__(self, api_key: str | None = None, timeout: int = 20):
        self.api_key = api_key or os.getenv("NEWSAPI_API_KEY")
        self.timeout = timeout

    def collect(self, start: datetime, end: datetime) -> list[RawItem]:
        if not self.api_key:
            raise SourceError("NEWSAPI_API_KEY 未設定")
        params = {
            "q": 'Trump OR "Donald Trump" OR "Truth Social"',
            "language": "en",
            "sortBy": "publishedAt",
            "pageSize": 100,
            "from": start.astimezone(timezone.utc).isoformat(),
            "to": end.astimezone(timezone.utc).isoformat(),
            "apiKey": self.api_key,
        }
        r = requests.get("https://newsapi.org/v2/everything", params=params, timeout=self.timeout)
        if r.status_code != 200:
            raise SourceError(f"NewsAPI HTTP {r.status_code}: {r.text[:200]}")
        out: list[RawItem] = []
        for i, article in enumerate(r.json().get("articles", []), start=1):
            source_name = (article.get("source") or {}).get("name") or "NewsAPI"
            out.append(RawItem(
                raw_item_id=f"NEWSAPI-{i:04d}",
                source_name=source_name,
                publisher_group=source_name,
                source_type="MEDIA_REPORT",
                published_at=datetime.fromisoformat(article["publishedAt"].replace("Z", "+00:00")),
                title=article.get("title") or "",
                body=article.get("description") or article.get("content") or "",
                url=article.get("url") or "",
                source_confidence=0.70, source_tier=4, source_role="SUPPLEMENT", acquisition_method="NEWSAPI",
            ))
        return out
