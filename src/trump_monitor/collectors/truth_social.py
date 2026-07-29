from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from urllib.parse import quote_plus
import html, json, os, re, xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
import requests

from trump_monitor.collectors.base import SourceAdapter, SourceError
from trump_monitor.models import RawItem


class TruthOfficialApiAdapter(SourceAdapter):
    """Tier-1 adapter for a licensed Truth API. Endpoint/JSON mapping is configurable."""
    name = "truth_official_api"

    def __init__(self, base_url: str, account: str = "realDonaldTrump", token: str | None = None, timeout: int = 20):
        self.base_url = base_url.rstrip("/")
        self.account = account
        self.token = token or os.getenv("TRUTH_API_TOKEN")
        self.timeout = timeout

    def collect(self, start: datetime, end: datetime) -> list[RawItem]:
        if not self.base_url or not self.token:
            raise SourceError("Truth API endpoint 或 TRUTH_API_TOKEN 未設定")
        headers = {"Authorization": f"Bearer {self.token}", "Accept": "application/json"}
        params = {"account": self.account, "from": start.isoformat(), "to": end.isoformat()}
        try:
            r = requests.get(self.base_url, headers=headers, params=params, timeout=self.timeout)
        except requests.RequestException as exc:
            raise SourceError(f"Truth API 連線失敗: {exc}") from exc
        if r.status_code == 401: raise SourceError("LOGIN_REQUIRED/UNAUTHORIZED")
        if r.status_code == 429: raise SourceError("RATE_LIMIT")
        if r.status_code != 200: raise SourceError(f"Truth API HTTP {r.status_code}")
        payload = r.json()
        posts = payload.get("posts", payload if isinstance(payload, list) else [])
        out=[]
        for post in posts:
            created = post.get("created_at") or post.get("published_at")
            if not created: continue
            dt = datetime.fromisoformat(str(created).replace("Z", "+00:00")).astimezone(timezone.utc)
            if not start <= dt <= end: continue
            text = re.sub(r"<[^>]+>", " ", str(post.get("content") or post.get("text") or ""))
            text = html.unescape(re.sub(r"\s+", " ", text)).strip()
            url = str(post.get("url") or post.get("uri") or "")
            pid = str(post.get("id") or sha256((url+created).encode()).hexdigest()[:16])
            out.append(RawItem(raw_item_id=f"TRUTH-{pid}", source_name="Truth Social", publisher_group="Truth Social",
                source_type="DIRECT_POST", published_at=dt, title=text[:120] or "Truth Social post", body=text, url=url,
                source_confidence=.98, direct_quote=True, source_tier=1, source_role="PRIMARY", acquisition_method="LICENSED_API", account_handle=self.account))
        return out


class TruthManualImportAdapter(SourceAdapter):
    """Tier-1 compliant fallback: user-provided JSON export or pasted posts."""
    name = "truth_manual_import"
    def __init__(self, path: str | Path, account: str = "realDonaldTrump"):
        self.path, self.account = Path(path), account
    def collect(self, start: datetime, end: datetime) -> list[RawItem]:
        if not self.path.exists(): return []
        try: rows=json.loads(self.path.read_text(encoding="utf-8"))
        except Exception as exc: raise SourceError(f"Truth人工匯入JSON錯誤: {exc}") from exc
        out=[]
        for i,row in enumerate(rows,1):
            dt=datetime.fromisoformat(str(row["published_at"]).replace("Z","+00:00")).astimezone(timezone.utc)
            if not start <= dt <= end: continue
            text=str(row.get("body") or row.get("text") or "").strip(); url=str(row.get("url") or "")
            out.append(RawItem(raw_item_id=str(row.get("raw_item_id") or f"TRUTH-MANUAL-{i:04d}"), source_name="Truth Social",
                publisher_group="Truth Social", source_type="DIRECT_POST", published_at=dt, title=str(row.get("title") or text[:120] or "Truth Social post"),
                body=text, url=url, source_confidence=.96, direct_quote=True, source_tier=1, source_role="MANUAL", acquisition_method="MANUAL_IMPORT", account_handle=self.account))
        return out


class TruthSearchIndexAdapter(SourceAdapter):
    """Tier-1 discovery without requesting Truth Social pages: finds indexed direct-post URLs via Google News RSS.
    The returned body is only the search snippet and is labeled SEARCH_INDEX, not a full-page scrape.
    """
    name = "truth_search_index"
    def __init__(self, account: str="realDonaldTrump", timeout: int=20): self.account, self.timeout=account, timeout
    def collect(self, start: datetime, end: datetime) -> list[RawItem]:
        query=f'site:truthsocial.com "@{self.account}" OR "Truth Social post" "{self.account}"'
        params={"q":query,"hl":"en-US","gl":"US","ceid":"US:en"}
        try:
            r=requests.get("https://news.google.com/rss/search",params=params,timeout=self.timeout,headers={"User-Agent":"TrumpEventMonitor/1.2"})
        except requests.RequestException as exc: raise SourceError(f"Truth搜尋索引連線失敗: {exc}") from exc
        if r.status_code!=200: raise SourceError(f"Truth搜尋索引 HTTP {r.status_code}")
        try: root=ET.fromstring(r.content)
        except ET.ParseError as exc: raise SourceError(f"Truth搜尋索引XML錯誤: {exc}") from exc
        out=[]
        for node in root.findall("./channel/item"):
            title=(node.findtext("title") or "").strip(); link=(node.findtext("link") or "").strip(); pub=(node.findtext("pubDate") or "").strip()
            desc=html.unescape(node.findtext("description") or ""); desc=re.sub(r"<[^>]+>"," ",desc); desc=re.sub(r"\s+"," ",desc).strip()
            try: dt=parsedate_to_datetime(pub).astimezone(timezone.utc)
            except Exception: continue
            if not start<=dt<=end: continue
            # Only accept records whose title/snippet/source explicitly indicates Truth Social or direct profile.
            if "truth social" not in (title+" "+desc).lower() and "truthsocial" not in link.lower(): continue
            rid="TRUTH-IDX-"+sha256((link+pub).encode()).hexdigest()[:16]
            out.append(RawItem(raw_item_id=rid,source_name="Truth Social (Search Index)",publisher_group="Truth Social",source_type="UNCONFIRMED",
                published_at=dt,title=title,body=desc,url=link,source_confidence=.58,direct_quote=False,source_tier=4,source_role="SUPPLEMENT",
                acquisition_method="SEARCH_INDEX",account_handle=self.account))
        return out
