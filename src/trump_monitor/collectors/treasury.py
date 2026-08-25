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

class TreasuryOfficialAdapter(SourceAdapter):
    """U.S. Treasury public press-release page; direct official URLs, no API key."""
    name="treasury_official"
    base_url="https://home.treasury.gov"
    listing="https://home.treasury.gov/news/press-releases"
    def __init__(self, timeout:int=10): self.timeout=timeout
    def collect(self,start:datetime,end:datetime)->list[RawItem]:
        try:
            r=requests.get(self.listing,timeout=self.timeout,headers={"User-Agent":"TrumpEventMonitor/2.3.16"}); r.raise_for_status()
            doc=lxml_html.fromstring(r.content)
        except Exception as exc:
            raise SourceError(f"Treasury 取得失敗: {type(exc).__name__}") from exc
        rows=[]; seen=set()
        for a in doc.xpath("//a[contains(@href,'/news/press-releases/')]"):
            href=str(a.get("href") or "").strip(); title=" ".join(a.text_content().split()).strip()
            if len(title)<12: continue
            url=urljoin(self.base_url,href)
            if url in seen: continue
            # Search the enclosing row/card for a human-readable date.
            node=a
            for _ in range(5):
                if node.getparent() is None: break
                node=node.getparent()
                text=" ".join(node.text_content().split())
                m=re.search(r"(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+20\d{2}",text)
                if m:
                    try: dt=date_parser.parse(m.group(0)).replace(tzinfo=timezone.utc)
                    except Exception: dt=None
                    break
            else: dt=None
            if not dt or not (start.date() <= dt.date() <= end.date()): continue
            seen.add(url); rid="UST-"+sha256(url.encode("utf-8")).hexdigest()[:16]
            rows.append(RawItem(raw_item_id=rid,source_name="U.S. Treasury",publisher_group="U.S. Treasury",source_type="OFFICIAL_POLICY",published_at=dt,title=title,body="",url=url,source_confidence=0.99,source_tier=1,source_role="PRIMARY",acquisition_method="TREASURY_PUBLIC_PAGE_DIRECT_URL",content_status="OFFICIAL_METADATA"))
        self.last_status=f"SUCCESS:{len(rows)}" if rows else "NO_DATA:0"
        return rows
