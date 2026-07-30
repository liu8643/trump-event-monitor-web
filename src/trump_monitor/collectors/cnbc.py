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


class CnbcNewsAdapter(SourceAdapter):
    """Explicit CNBC source collected through Google News RSS source filtering.

    This preserves the original no-key Google News RSS mechanism, while giving CNBC
    its own adapter name, source status, source count and UI/report visibility.
    It does not claim to be a CNBC licensed/full-text API.
    """

    name = "cnbc"

    def __init__(self, query: str = '(Donald Trump OR "Truth Social") source:CNBC', timeout: int = 20,
                 language: str = "en-US", country: str = "US"):
        self.query = query
        self.timeout = timeout
        self.language = language
        self.country = country

    def collect(self, start: datetime, end: datetime) -> list[RawItem]:
        params = {"q": self.query, "hl": self.language, "gl": self.country, "ceid": f"{self.country}:en"}
        try:
            response = requests.get(
                "https://news.google.com/rss/search",
                params=params,
                timeout=self.timeout,
                headers={"User-Agent": "TrumpEventMonitor/2.2.2 (+https://github.com/)"},
            )
        except requests.RequestException as exc:
            raise SourceError(f"CNBC RSS 連線失敗: {exc}") from exc
        if response.status_code != 200:
            raise SourceError(f"CNBC RSS HTTP {response.status_code}")
        try:
            root = ET.fromstring(response.content)
        except ET.ParseError as exc:
            raise SourceError(f"CNBC RSS XML 解析失敗: {exc}") from exc

        rows: list[RawItem] = []
        for node in root.findall("./channel/item"):
            title = (node.findtext("title") or "").strip()
            link = (node.findtext("link") or "").strip()
            pub_text = (node.findtext("pubDate") or "").strip()
            source_node = node.find("source")
            source_name = (source_node.text or "").strip() if source_node is not None else ""
            source_url = (source_node.attrib.get("url", "") if source_node is not None else "").lower()
            # Do not allow the source-specific adapter to relabel other publishers as CNBC.
            if "cnbc" not in source_name.lower() and "cnbc.com" not in source_url:
                continue
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
            raw_id = "CNBC-" + sha256(f"{link}|{pub_text}".encode("utf-8")).hexdigest()[:16]
            rows.append(RawItem(
                raw_item_id=raw_id,
                source_name="CNBC",
                publisher_group="CNBC",
                source_type="MEDIA_REPORT",
                published_at=published,
                title=title,
                body=description,
                url=link,
                source_confidence=0.86,
                source_tier=2,
                source_role="VERIFICATION",
                acquisition_method="CNBC_GOOGLE_NEWS_RSS",
            ))
        return rows
