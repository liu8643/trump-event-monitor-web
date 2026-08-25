from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import shutil
from urllib.parse import quote_plus
import html, json, os, re, xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
import requests

from trump_monitor.collectors.base import SourceAdapter, SourceError
from trump_monitor.models import RawItem, SourceObservation


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
        account_id: str = "107780257626128497",
        timeout: int = 20,
        max_pages: int = 8,
        page_size: int = 40,
        session: requests.Session | None = None,
        rendered_html_enabled: bool = True,
        static_html_enabled: bool = True,
        rendered_timeout: int = 25,
        chromium_executable: str = "",
    ):
        from urllib.parse import urlsplit

        parts = urlsplit(profile_url)
        if parts.scheme not in {"http", "https"} or not parts.netloc:
            raise ValueError("Truth Social profile_url 格式錯誤")
        self.profile_url = profile_url
        self.base_url = f"{parts.scheme}://{parts.netloc}"
        profile_handle = parts.path.strip("/").split("/")[0].lstrip("@") if parts.path else ""
        self.account = account or profile_handle or "realDonaldTrump"
        self.account_id = str(account_id or "").strip()
        self.timeout = timeout
        self.max_pages = max(1, int(max_pages))
        self.page_size = min(40, max(1, int(page_size)))
        self.session = session or requests.Session()
        self.rendered_html_enabled = bool(rendered_html_enabled)
        self.static_html_enabled = bool(static_html_enabled)
        self.rendered_timeout = max(5, int(rendered_timeout))
        self.chromium_executable = str(chromium_executable or "").strip()
        self.last_status = "NOT_RUN"
        self.last_observations: list[SourceObservation] = []
        self.headers = {
            "Accept": "application/json",
            "User-Agent": "TrumpEventMonitor/2.2 (+TruthOfficialTimeline)",
            "Referer": self.profile_url,
        }

    def _get_json(self, url: str, params: dict | None = None, endpoint_name: str = "endpoint"):
        """GET a public JSON endpoint and preserve actionable failure details.

        Truth Social may treat the account lookup endpoint differently from the
        account-status endpoint.  The endpoint name is therefore included in the
        error so the UI can distinguish LOOKUP_DENIED from STATUSES_DENIED.
        """
        try:
            response = self.session.get(url, params=params, headers=self.headers, timeout=self.timeout)
        except requests.RequestException as exc:
            raise SourceError(f"{endpoint_name}_CONNECTION_FAILED: {exc}") from exc
        if response.status_code == 401:
            raise SourceError(f"{endpoint_name}_LOGIN_REQUIRED/HTTP_401")
        if response.status_code == 403:
            server = response.headers.get("server", "") if hasattr(response, "headers") else ""
            ray = response.headers.get("cf-ray", "") if hasattr(response, "headers") else ""
            suffix = ":".join(x for x in (server, ray) if x)
            raise SourceError(f"{endpoint_name}_ACCESS_DENIED/HTTP_403" + (f":{suffix}" if suffix else ""))
        if response.status_code == 429:
            raise SourceError(f"{endpoint_name}_RATE_LIMIT/HTTP_429")
        if response.status_code != 200:
            raise SourceError(f"{endpoint_name}_HTTP_{response.status_code}")
        try:
            return response.json()
        except Exception as exc:
            raise SourceError(f"{endpoint_name}_NON_JSON_RESPONSE") from exc

    @staticmethod
    def _clean_content(value: object) -> str:
        text = re.sub(r"<br\s*/?>", "\n", str(value or ""), flags=re.I)
        text = re.sub(r"</p>", "\n", text, flags=re.I)
        text = re.sub(r"<[^>]+>", " ", text)
        text = html.unescape(text)
        return re.sub(r"[ \t]+", " ", re.sub(r"\n{3,}", "\n\n", text)).strip()

    def _collect_json(self, start: datetime, end: datetime) -> list[RawItem]:
        start = start.astimezone(timezone.utc)
        end = end.astimezone(timezone.utc)
        # Prefer the configured stable account ID.  The public lookup endpoint is
        # currently more likely to be blocked by the platform/WAF than the statuses
        # endpoint.  Falling back to lookup remains available for other accounts.
        account_id = self.account_id
        if not account_id:
            account_data = self._get_json(
                f"{self.base_url}/api/v1/accounts/lookup",
                {"acct": self.account},
                endpoint_name="ACCOUNT_LOOKUP",
            )
            account_id = str(account_data.get("id") or "").strip() if isinstance(account_data, dict) else ""
            account_acct = str(account_data.get("acct") or account_data.get("username") or "") if isinstance(account_data, dict) else ""
            if not account_id:
                raise SourceError("ACCOUNT_LOOKUP_NO_ACCOUNT_ID")
            if account_acct and account_acct.split("@")[0].lower() != self.account.lower():
                raise SourceError(f"ACCOUNT_LOOKUP_ACCOUNT_MISMATCH:{account_acct}")

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
            payload = self._get_json(
                f"{self.base_url}/api/v1/accounts/{quote_plus(account_id)}/statuses",
                params,
                endpoint_name="ACCOUNT_STATUSES",
            )
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


    def _observation(self, layer: str, status: str, displayed_text: str = "", note: str = "", eligible: bool = False, quality: str = "NONE") -> SourceObservation:
        return SourceObservation(
            source_key=self.name,
            layer=layer,
            status=status,
            url=self.profile_url,
            displayed_text=displayed_text[:2000],
            note=note[:2000],
            observed_at=datetime.now(timezone.utc),
            eligible_for_event_engine=eligible,
            evidence_quality=quality,
        )

    def _collect_rendered_html(self, start: datetime, end: datetime) -> list[RawItem]:
        """Best-effort browser rendering. It never bypasses login or access controls."""
        try:
            from playwright.sync_api import sync_playwright
        except Exception as exc:
            self.last_observations.append(self._observation(
                "RENDERED_HTML", "RENDERER_NOT_AVAILABLE", note=f"Playwright unavailable: {type(exc).__name__}"
            ))
            return []
        rows: list[RawItem] = []
        try:
            with sync_playwright() as pw:
                executable = (
                    self.chromium_executable
                    or os.getenv("PLAYWRIGHT_CHROMIUM_EXECUTABLE", "")
                    or shutil.which("chromium")
                    or shutil.which("chromium-browser")
                    or shutil.which("google-chrome")
                    or shutil.which("google-chrome-stable")
                    or ""
                )
                launch_kwargs = {
                    "headless": True,
                    "args": ["--no-sandbox", "--disable-dev-shm-usage"],
                }
                if executable:
                    launch_kwargs["executable_path"] = executable
                browser = pw.chromium.launch(**launch_kwargs)
                page = browser.new_page(user_agent=self.headers["User-Agent"])
                page.goto(self.profile_url, wait_until="domcontentloaded", timeout=self.rendered_timeout * 1000)
                page.wait_for_timeout(3500)
                body_text = (page.locator("body").inner_text(timeout=5000) or "").strip()
                if re.search(r"log\s*in|sign\s*in", body_text, re.I) and len(body_text) < 1200:
                    self.last_observations.append(self._observation("RENDERED_HTML", "LOGIN_REQUIRED", body_text, "公開頁要求登入；請由官方網址自行查閱。"))
                    browser.close(); return []
                candidates = page.locator("article, [data-testid='status'], .status, .entry").all()
                for idx, node in enumerate(candidates[:80]):
                    try:
                        text=(node.inner_text(timeout=1500) or "").strip()
                    except Exception:
                        continue
                    if len(text) < 15:
                        continue
                    link=""
                    try:
                        href=node.locator("a[href*='/@realDonaldTrump/']").first.get_attribute("href") or ""
                        link = href if href.startswith("http") else self.base_url + href
                    except Exception:
                        pass
                    dt=end
                    try:
                        raw_dt=node.locator("time").first.get_attribute("datetime") or ""
                        if raw_dt: dt=datetime.fromisoformat(raw_dt.replace("Z", "+00:00")).astimezone(timezone.utc)
                    except Exception:
                        pass
                    if not start <= dt <= end:
                        continue
                    rid=sha256((link+text[:200]).encode()).hexdigest()[:16]
                    rows.append(RawItem(
                        raw_item_id=f"TRUTH-RENDERED-{rid}", source_name="Truth Social Rendered Public Page",
                        publisher_group="Truth Social Official", source_type="DIRECT_POST", published_at=dt,
                        title=text[:160], body=text, url=link or self.profile_url, source_confidence=.82,
                        direct_quote=True, source_tier=2, source_role="VERIFICATION",
                        acquisition_method="RENDERED_PUBLIC_PAGE", account_handle=self.account,
                        content_status="SUCCESS_RENDERED_PARTIAL", ai_summary_status="PENDING_ANALYSIS",
                    ))
                browser.close()
                if rows:
                    self.last_observations.append(self._observation("RENDERED_HTML", "SUCCESS_RENDERED_PARTIAL", f"Rendered posts: {len(rows)}", "畫面可見內容已記錄；可能不是完整時間軸。", True, "PARTIAL_FIRST_PARTY"))
                else:
                    low=body_text.lower()
                    is_cf=("performing security verification" in low or "cloudflare" in low or "ray id:" in low or "enable javascript and cookies" in low)
                    if is_cf:
                        status="ACCESS_DENIED_CLOUDFLARE_CHALLENGE"
                        note="Rendered page is a Cloudflare/security verification challenge, not a valid no-posts timeline."
                    elif "enable javascript" in low:
                        status="STATIC_HTML_JS_REQUIRED"
                        note="公開頁需要JavaScript，未辨識到可送入事件引擎的貼文。"
                    else:
                        status="RENDERED_NO_POSTS"
                        note="頁面正常載入但未辨識到可送入事件引擎的公開貼文；請點官方頁查閱。"
                    self.last_observations.append(self._observation("RENDERED_HTML", status, body_text, note))
        except Exception as exc:
            message = f"{type(exc).__name__}: {exc}"
            status = "RENDERER_BROWSER_MISSING" if "Executable doesn't exist" in message or "playwright install" in message.lower() else "RENDERED_HTML_FAILED"
            self.last_observations.append(self._observation("RENDERED_HTML", status, note=message[:2000]))
        rows.sort(key=lambda item: item.published_at)
        return rows

    def _collect_static_html(self) -> None:
        if not self.static_html_enabled:
            return
        try:
            r=self.session.get(self.profile_url, headers={"User-Agent": self.headers["User-Agent"], "Accept": "text/html"}, timeout=self.timeout)
            text=self._clean_content(getattr(r,"text",""))
            low=text.lower()
            is_cf = (
                "just a moment" in low
                or "cf_chl" in low
                or "enable javascript and cookies to continue" in low
                or "cloudflare" in low
            )
            if r.status_code == 401:
                status="LOGIN_REQUIRED"
            elif r.status_code == 403 and is_cf:
                status="ACCESS_DENIED_CLOUDFLARE_CHALLENGE"
            elif r.status_code == 403:
                status="ACCESS_DENIED"
            elif r.status_code == 429:
                status="RATE_LIMIT"
            elif r.status_code != 200:
                status=f"STATIC_HTML_HTTP_{r.status_code}"
            elif "enable javascript" in low:
                status="STATIC_HTML_PAGE_SHELL"
            elif text:
                status="STATIC_HTML_VISIBLE_TEXT"
            else:
                status="STATIC_HTML_EMPTY"
            if is_cf:
                display = "Just a moment... Enable JavaScript and cookies to continue. (Cloudflare challenge page)"
            elif status == "STATIC_HTML_PAGE_SHELL":
                display = text[:500]
            else:
                display = text[:2000]
            note="公開頁可開啟，但未取得可送入事件引擎的貼文正文；請點擊官方頁面自行查閱。"
            self.last_observations.append(self._observation("STATIC_HTML", status, display, note, False, "REFERENCE_ONLY"))
        except requests.RequestException as exc:
            self.last_observations.append(self._observation("STATIC_HTML", "STATIC_HTML_CONNECTION_FAILED", note=str(exc)))

    def collect(self, start: datetime, end: datetime) -> list[RawItem]:
        self.last_observations=[]
        json_error=""
        try:
            rows=self._collect_json(start,end)
            if rows:
                self.last_status=f"SUCCESS_FULL_TEXT:{len(rows)}"
                self.last_observations.append(self._observation("OFFICIAL_TIMELINE_JSON", "SUCCESS_FULL_TEXT", f"Official posts: {len(rows)}", "完整JSON貼文已送入事件引擎。", True, "PRIMARY"))
                return rows
            self.last_observations.append(self._observation("OFFICIAL_TIMELINE_JSON", "NO_POSTS_IN_72H", note="JSON端點成功，但72小時內沒有貼文。"))
        except SourceError as exc:
            json_error=str(exc)
            self.last_observations.append(self._observation("OFFICIAL_TIMELINE_JSON", json_error, note="JSON端點失敗，繼續Rendered/Static HTML備援。"))
        rendered=[]
        if self.rendered_html_enabled:
            rendered=self._collect_rendered_html(start,end)
        if rendered:
            self.last_status=f"SUCCESS_RENDERED_PARTIAL:{len(rendered)}"
            return rendered
        self._collect_static_html()
        self.last_observations.append(self._observation(
            "MANUAL_REVIEW",
            "MANUAL_REVIEW_AVAILABLE",
            displayed_text="Truth Official 公開頁可由使用者自行開啟查閱。",
            note="自動來源未取得可送入事件引擎的完整貼文；請使用官方網址人工確認。",
            eligible=False,
            quality="MANUAL_REFERENCE",
        ))
        statuses=[o.status for o in self.last_observations]
        if "STATIC_HTML_PAGE_SHELL" in statuses:
            self.last_status="STATIC_HTML_PAGE_SHELL"
        elif "LOGIN_REQUIRED" in statuses:
            self.last_status="LOGIN_REQUIRED"
        elif "ACCESS_DENIED" in statuses or any("ACCESS_DENIED" in x for x in statuses):
            self.last_status="ACCESS_DENIED"
        elif "RATE_LIMIT" in statuses or any("RATE_LIMIT" in x for x in statuses):
            self.last_status="RATE_LIMIT"
        elif "NO_POSTS_IN_72H" in statuses:
            self.last_status="NO_POSTS_IN_72H"
        else:
            self.last_status=json_error or (statuses[-1] if statuses else "NO_DATA")
        return []


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
