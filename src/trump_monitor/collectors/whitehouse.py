from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from urllib.parse import urljoin
import re

import requests
from dateutil import parser as date_parser
from lxml import html as lxml_html

from trump_monitor.collectors.base import SourceAdapter, SourceError
from trump_monitor.models import RawItem


class WhiteHouseOfficialAdapter(SourceAdapter):
    """Public White House pages as a first-party source with direct URLs."""

    name = "whitehouse_official"
    base_url = "https://www.whitehouse.gov"
    sections = (
        "/releases/",
        "/briefings-statements/",
        "/remarks/",
        "/presidential-actions/",
    )

    def __init__(self, timeout: int = 15):
        self.timeout = timeout

    @staticmethod
    def _date_from_node(node) -> datetime | None:
        for raw in node.xpath(".//time/@datetime"):
            try:
                dt = date_parser.parse(raw)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.astimezone(timezone.utc)
            except Exception:
                pass
        text = " ".join(node.text_content().split())
        match = re.search(r"(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+20\d{2}", text)
        if match:
            try:
                return date_parser.parse(match.group(0)).replace(tzinfo=timezone.utc)
            except Exception:
                return None
        return None

    def collect(self, start: datetime, end: datetime) -> list[RawItem]:
        rows: list[RawItem] = []
        seen: set[str] = set()
        failures: list[str] = []
        for section in self.sections:
            url = urljoin(self.base_url, section)
            try:
                r = requests.get(url, timeout=self.timeout, headers={"User-Agent": "TrumpEventMonitor/2.3.11"})
                if r.status_code != 200:
                    failures.append(f"{section}:{r.status_code}")
                    continue
                doc = lxml_html.fromstring(r.content)
            except Exception as exc:
                failures.append(f"{section}:{type(exc).__name__}")
                continue
            nodes = doc.xpath("//article | //li[.//a[contains(@href,'whitehouse.gov') or starts-with(@href,'/')]]")
            if not nodes:
                nodes = doc.xpath("//a[@href]")
            for node in nodes:
                links = node.xpath(".//a[@href]") if getattr(node, "tag", "") != "a" else [node]
                if not links:
                    continue
                a = links[0]
                href = str(a.get("href") or "").strip()
                title = " ".join(a.text_content().split()).strip()
                if not href or len(title) < 12:
                    continue
                direct = urljoin(self.base_url, href)
                if "whitehouse.gov" not in direct or direct in seen:
                    continue
                dt = self._date_from_node(node)
                if dt is None or not (start <= dt <= end):
                    continue
                seen.add(direct)
                rid = "WH-" + sha256(direct.encode("utf-8")).hexdigest()[:16]
                rows.append(RawItem(
                    raw_item_id=rid,
                    source_name="The White House",
                    publisher_group="The White House",
                    source_type="OFFICIAL_POLICY",
                    published_at=dt,
                    title=title,
                    body="",
                    url=direct,
                    source_confidence=0.99,
                    source_tier=1,
                    source_role="PRIMARY",
                    acquisition_method="WHITE_HOUSE_PUBLIC_PAGE",
                    content_status="OFFICIAL_METADATA",
                ))
        if not rows and failures and len(failures) == len(self.sections):
            raise SourceError("White House 全部頁面失敗: " + ",".join(failures))
        rows.sort(key=lambda x: x.published_at)
        return rows
