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


class TruthTimelineCollector(SourceAdapter):
    """Collect public posts from the configured Truth Social official profile timeline.

    The collector treats ``truth_profile_url`` as the authoritative profile source,
    resolves the configured handle through Truth Social's Mastodon-compatible JSON
    endpoints on the same host, orders posts by ``created_at`` and applies the engine's
    requested [start, end] time window. It does not replace the licensed API, manual
    import, or search-index adapters; it is an additional highest-priority source.
    """

    name = "truth_official_timeline"

    def __init__(
        self,
        profile_url: str = "https://truthsocial.com/@realDonaldTrump",
        account: str = "realDonaldTrump",
        timeout: int = 20,
        max_pages: int = 8,
        page_size: int = 40,
        session: requests.Session | None = None,
    ):
        from urllib.parse import urlsplit

        parts = urlsplit(profile_url)
        if parts.scheme not in {"http", "https"} or not parts.netloc:
            raise ValueError("Truth Social profile_url 格式錯誤")
        self.profile_url = profile_url
        self.base_url = f"{parts.scheme}://{parts.netloc}"
        profile_handle = parts.path.strip("/").split("/")[0].lstrip("@") if parts.path else ""
        self.account = account or profile_handle or "realDonaldTrump"
        self.timeout = timeout
        self.max_pages = max(1, int(max_pages))
        self.page_size = min(40, max(1, int(page_size)))
        self.session = session or requests.Session()
        self.headers = {
            "Accept": "application/json",
            "User-Agent": "TrumpEventMonitor/2.2 (+TruthOfficialTimeline)",
            "Referer": self.profile_url,
        }

    def _get_json(self, url: str, params: dict | None = None):
        try:
            response = self.session.get(url, params=params, headers=self.headers, timeout=self.timeout)
        except requests.RequestException as exc:
            raise SourceError(f"Truth Official Timeline 連線失敗: {exc}") from exc
        if response.status_code == 401:
            raise SourceError("LOGIN_REQUIRED/UNAUTHORIZED")
        if response.status_code == 403:
            raise SourceError("ACCESS_DENIED/HTTP_403")
        if response.status_code == 429:
            raise SourceError("RATE_LIMIT/HTTP_429")
        if response.status_code != 200:
            raise SourceError(f"Truth Official Timeline HTTP {response.status_code}")
        try:
            return response.json()
        except Exception as exc:
            raise SourceError("Truth Official Timeline 回傳非JSON；公開時間軸端點可能已變更") from exc

    @staticmethod
    def _clean_content(value: object) -> str:
        text = re.sub(r"<br\s*/?>", "\n", str(value or ""), flags=re.I)
        text = re.sub(r"</p>", "\n", text, flags=re.I)
        text = re.sub(r"<[^>]+>", " ", text)
        text = html.unescape(text)
        return re.sub(r"[ \t]+", " ", re.sub(r"\n{3,}", "\n\n", text)).strip()

    def collect(self, start: datetime, end: datetime) -> list[RawItem]:
        start = start.astimezone(timezone.utc)
        end = end.astimezone(timezone.utc)
        account_data = self._get_json(
            f"{self.base_url}/api/v1/accounts/lookup",
            {"acct": self.account},
        )
        account_id = str(account_data.get("id") or "").strip() if isinstance(account_data, dict) else ""
        account_acct = str(account_data.get("acct") or account_data.get("username") or "") if isinstance(account_data, dict) else ""
        if not account_id:
            raise SourceError("Truth Official Timeline 找不到帳號ID")
        if account_acct and account_acct.split("@")[0].lower() != self.account.lower():
            raise SourceError(f"Truth Official Timeline 帳號驗證不符: {account_acct}")

        out: list[RawItem] = []
        max_id: str | None = None
        reached_older = False
        for _ in range(self.max_pages):
            params = {
                "limit": self.page_size,
                "exclude_replies": "true",
                "exclude_reblogs": "true",
            }
            if max_id:
                params["max_id"] = max_id
            payload = self._get_json(f"{self.base_url}/api/v1/accounts/{quote_plus(account_id)}/statuses", params)
            if not isinstance(payload, list) or not payload:
                break
            page_oldest: datetime | None = None
            for post in payload:
                if not isinstance(post, dict):
                    continue
                created = post.get("created_at")
                if not created:
                    continue
                try:
                    dt = datetime.fromisoformat(str(created).replace("Z", "+00:00")).astimezone(timezone.utc)
                except ValueError:
                    continue
                page_oldest = dt if page_oldest is None or dt < page_oldest else page_oldest
                if dt < start:
                    reached_older = True
                    continue
                if dt > end:
                    continue
                text = self._clean_content(post.get("content") or post.get("text"))
                if not text:
                    text = "[媒體貼文：未提供文字]" if post.get("media_attachments") else ""
                url = str(post.get("url") or post.get("uri") or "").strip()
                post_id = str(post.get("id") or sha256((url + str(created)).encode()).hexdigest()[:16])
                out.append(RawItem(
                    raw_item_id=f"TRUTH-TIMELINE-{post_id}",
                    source_name="Truth Social Official Timeline",
                    publisher_group="Truth Social Official",
                    source_type="DIRECT_POST",
                    published_at=dt,
                    title=text[:160] or "Truth Social official post",
                    body=text,
                    url=url or self.profile_url,
                    source_confidence=.99,
                    direct_quote=True,
                    source_tier=1,
                    source_role="PRIMARY",
                    acquisition_method="TRUTH_OFFICIAL_TIMELINE_PUBLIC_JSON",
                    account_handle=self.account,
                    content_status="PUBLIC_OFFICIAL_TIMELINE",
                    ai_summary_status="PENDING_ANALYSIS",
                ))
            last_id = str(payload[-1].get("id") or "") if isinstance(payload[-1], dict) else ""
            if reached_older or len(payload) < self.page_size or not last_id or last_id == max_id:
                break
            max_id = last_id
            if page_oldest and page_oldest < start:
                break

        # The API commonly returns newest first. Explicit sorting is required by the V2.2 design.
        out.sort(key=lambda item: item.published_at)
        return out


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
            out.append(RawItem(raw_item_id=rid,source_name="Truth Social (Search Index)",publisher_group="Truth Social",source_type="DIRECT_POST",
                published_at=dt,title=title,body=desc,url=link,source_confidence=.72,direct_quote=False,source_tier=1,source_role="PRIMARY",
                acquisition_method="SEARCH_INDEX",account_handle=self.account))
        return out
