from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from hashlib import sha256
import html
import re
import xml.etree.ElementTree as ET
import requests

from trump_monitor.collectors.base import SourceAdapter, SourceError
from trump_monitor.models import RawItem
from trump_monitor.collectors.source_policy import publisher_tier


class GoogleNewsRssAdapter(SourceAdapter):
    """No-key real-news source using Google News RSS search results."""

    name = "google_news_rss"

    def __init__(self, query: str = 'Donald Trump OR "Truth Social"', timeout: int = 20, language: str = "en-US", country: str = "US"):
        self.query = query
        self.timeout = timeout
        self.language = language
        self.country = country

    def collect(self, start: datetime, end: datetime) -> list[RawItem]:
        params = {
            "q": self.query,
            "hl": self.language,
            "gl": self.country,
            "ceid": f"{self.country}:en",
        }
        try:
            response = requests.get(
                "https://news.google.com/rss/search",
                params=params,
                timeout=self.timeout,
                headers={"User-Agent": "TrumpEventMonitor/1.1 (+https://github.com/)"},
            )
        except requests.RequestException as exc:
            raise SourceError(f"Google News RSS 連線失敗: {exc}") from exc
        if response.status_code != 200:
            raise SourceError(f"Google News RSS HTTP {response.status_code}")
        try:
            root = ET.fromstring(response.content)
        except ET.ParseError as exc:
            raise SourceError(f"Google News RSS XML 解析失敗: {exc}") from exc

        items: list[RawItem] = []
        for node in root.findall("./channel/item"):
            title = (node.findtext("title") or "").strip()
            link = (node.findtext("link") or "").strip()
            pub_text = (node.findtext("pubDate") or "").strip()
            source_node = node.find("source")
            source_name = (source_node.text or "Google News") if source_node is not None else "Google News"
            description = html.unescape(node.findtext("description") or "")
            description = re.sub(r"<[^>]+>", " ", description)
            description = re.sub(r"\s+", " ", description).strip()
            if not title or not link or not pub_text:
                continue
            try:
                published = parsedate_to_datetime(pub_text)
                if published.tzinfo is None:
                    published = published.replace(tzinfo=timezone.utc)
                published = published.astimezone(timezone.utc)
            except (TypeError, ValueError):
                continue
            if not (start <= published <= end):
                continue
            raw_id = "GNRSS-" + sha256(f"{link}|{pub_text}".encode("utf-8")).hexdigest()[:16]
            tier, role = publisher_tier(source_name)
            items.append(RawItem(
                raw_item_id=raw_id,
                source_name=source_name.strip(),
                publisher_group=source_name.strip(),
                source_type="MEDIA_REPORT",
                published_at=published,
                title=title,
                body=description,
                url=link,
                source_confidence=0.90 if tier == 2 else 0.68,
                source_tier=tier, source_role=role, acquisition_method="GOOGLE_NEWS_RSS",
            ))
        return items
