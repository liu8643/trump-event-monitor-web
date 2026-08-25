from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from urllib.parse import urlsplit

import requests

from trump_monitor.collectors.base import SourceAdapter, SourceError
from trump_monitor.collectors.source_policy import publisher_tier
from trump_monitor.models import RawItem


class GdeltDocAdapter(SourceAdapter):
    """No-key GDELT DOC 2.0 discovery source returning direct publisher URLs.

    GDELT is used as an independent discovery channel beside Google News RSS.
    It provides article metadata/URLs only; this adapter never bypasses paywalls.
    """

    name = "gdelt"
    endpoint = "https://api.gdeltproject.org/api/v2/doc/doc"

    def __init__(self, query: str = '"Donald Trump" OR Trump', timeout: int = 20, max_records: int = 250):
        self.query = query
        self.timeout = timeout
        self.max_records = min(max(10, int(max_records)), 250)

    @staticmethod
    def _parse_dt(value: str) -> datetime | None:
        raw = (value or "").strip()
        if not raw:
            return None
        candidates = [raw, raw.replace("Z", "+00:00")]
        for item in candidates:
            try:
                dt = datetime.fromisoformat(item)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.astimezone(timezone.utc)
            except ValueError:
                pass
        for fmt in ("%Y%m%dT%H%M%SZ", "%Y%m%d%H%M%S"):
            try:
                return datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
            except ValueError:
                pass
        return None

    def collect(self, start: datetime, end: datetime) -> list[RawItem]:
        params = {
            "query": self.query,
            "mode": "ArtList",
            "format": "json",
            "maxrecords": self.max_records,
            "startdatetime": start.astimezone(timezone.utc).strftime("%Y%m%d%H%M%S"),
            "enddatetime": end.astimezone(timezone.utc).strftime("%Y%m%d%H%M%S"),
            "sort": "DateDesc",
        }
        try:
            r = requests.get(self.endpoint, params=params, timeout=self.timeout, headers={"User-Agent": "TrumpEventMonitor/2.3.11"})
        except requests.RequestException as exc:
            raise SourceError(f"GDELT 連線失敗: {exc}") from exc
        if r.status_code != 200:
            raise SourceError(f"GDELT HTTP {r.status_code}: {r.text[:160]}")
        try:
            payload = r.json()
        except ValueError as exc:
            raise SourceError("GDELT JSON 解析失敗") from exc
        articles = payload.get("articles", []) if isinstance(payload, dict) else []
        rows: list[RawItem] = []
        for article in articles:
            if not isinstance(article, dict):
                continue
            url = str(article.get("url") or "").strip()
            title = str(article.get("title") or "").strip()
            dt = self._parse_dt(str(article.get("seendate") or article.get("date") or ""))
            if not url or not title or dt is None or not (start <= dt <= end):
                continue
            domain = str(article.get("domain") or urlsplit(url).netloc or "GDELT").strip().lower()
            publisher = domain.removeprefix("www.") or "GDELT"
            tier, role = publisher_tier(publisher)
            rid = "GDELT-" + sha256(f"{url}|{dt.isoformat()}".encode("utf-8")).hexdigest()[:16]
            rows.append(RawItem(
                raw_item_id=rid,
                source_name=publisher,
                publisher_group=publisher,
                source_type="MEDIA_REPORT",
                published_at=dt,
                title=title,
                body="",
                url=url,
                source_confidence=0.88 if tier == 2 else 0.66,
                source_tier=tier,
                source_role=role,
                acquisition_method="GDELT_DOC_API_DIRECT_URL",
                content_status="METADATA_ONLY",
            ))
        return rows
