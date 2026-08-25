from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from urllib.parse import urlsplit
import json
import os
from pathlib import Path
import time

import requests

from trump_monitor.collectors.base import SourceAdapter, SourceError
from trump_monitor.collectors.source_policy import publisher_tier
from trump_monitor.logging_utils import get_logger
from trump_monitor.models import RawItem

logger = get_logger("gdelt")


class GdeltDocAdapter(SourceAdapter):
    """No-key GDELT DOC discovery source returning direct publisher URLs.

    The public endpoint can reply with a rate-limit/plain-text message even when
    HTTP status is 200.  V2.3.15 treats rate limiting as a persisted degraded-source circuit, with
    the required spacing, and then falls back to clearly labeled recent cache.
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
        for item in (raw, raw.replace("Z", "+00:00")):
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

    @staticmethod
    def _looks_rate_limited(text: str) -> bool:
        low = " ".join((text or "").lower().split())
        return any(x in low for x in ("rate limit", "one request every", "one request per", "please limit", "too many requests", "429"))

    def _cache_path(self) -> Path:
        return Path(os.getenv("GDELT_CACHE_PATH", "output/gdelt_articles_cache.json"))

    def _state_path(self) -> Path:
        configured=os.getenv("GDELT_STATE_PATH","").strip()
        if configured:
            return Path(configured)
        cache=self._cache_path()
        return cache.with_name("gdelt_runtime_state.json")

    def _circuit_state(self) -> tuple[datetime | None, str]:
        try:
            p=self._state_path()
            if not p.exists(): return None, ""
            data=json.loads(p.read_text(encoding="utf-8"))
            raw=str(data.get("blocked_until") or "") if isinstance(data,dict) else ""
            reason=str(data.get("reason") or "") if isinstance(data,dict) else ""
            if not raw: return None, reason
            dt=datetime.fromisoformat(raw.replace("Z","+00:00"))
            if dt.tzinfo is None: dt=dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc), reason
        except Exception:
            return None, ""

    def _mark_circuit(self, reason: str) -> None:
        seconds=max(60.0,float(os.getenv("GDELT_CIRCUIT_SECONDS","1800")))
        until=datetime.now(timezone.utc).timestamp()+seconds
        dt=datetime.fromtimestamp(until,tz=timezone.utc)
        try:
            p=self._state_path(); p.parent.mkdir(parents=True,exist_ok=True)
            tmp=p.with_suffix(p.suffix+".tmp")
            tmp.write_text(json.dumps({"blocked_until":dt.isoformat(),"reason":reason[:240]},ensure_ascii=False),encoding="utf-8")
            tmp.replace(p)
        except Exception as exc:
            logger.warning("gdelt circuit persist failed | %s", type(exc).__name__)

    def _circuit_open(self) -> tuple[bool, str]:
        until, reason=self._circuit_state()
        return (bool(until and until>datetime.now(timezone.utc)), reason)

    def _load_cached_articles(self) -> list[dict]:
        try:
            p = self._cache_path()
            if not p.exists():
                return []
            data = json.loads(p.read_text(encoding="utf-8"))
            return data.get("articles", []) if isinstance(data, dict) else []
        except Exception:
            return []

    def _save_cached_articles(self, articles: list[dict]) -> None:
        try:
            p = self._cache_path(); p.parent.mkdir(parents=True, exist_ok=True)
            tmp = p.with_suffix(p.suffix + ".tmp")
            tmp.write_text(json.dumps({"saved_at": datetime.now(timezone.utc).isoformat(), "articles": articles}, ensure_ascii=False), encoding="utf-8")
            tmp.replace(p)
        except Exception as exc:
            logger.warning("gdelt cache persist failed | %s", type(exc).__name__)

    def _rows_from_articles(self, articles: list[dict], start: datetime, end: datetime, cached: bool = False) -> list[RawItem]:
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
                raw_item_id=rid, source_name=publisher, publisher_group=publisher,
                source_type="MEDIA_REPORT", published_at=dt, title=title, body="", url=url,
                source_confidence=0.84 if cached and tier == 2 else 0.62 if cached else 0.88 if tier == 2 else 0.66,
                source_tier=tier, source_role=role,
                acquisition_method="GDELT_DOC_API_DIRECT_URL_CACHE" if cached else "GDELT_DOC_API_DIRECT_URL",
                content_status="METADATA_ONLY_CACHE" if cached else "METADATA_ONLY",
            ))
        return rows

    def _cached_or_raise(self, start: datetime, end: datetime, last_error: str) -> list[RawItem]:
        cached_rows = self._rows_from_articles(self._load_cached_articles(), start, end, cached=True)
        if cached_rows:
            self.last_status = f"SUCCESS_CACHE:{len(cached_rows)};LIVE_ERROR={last_error[:120]}"
            logger.warning("gdelt live degraded, cache used | rows=%d | error=%s", len(cached_rows), last_error[:160])
            return cached_rows
        raise SourceError(last_error or "GDELT 無可用資料")

    def _cached_or_degraded(self, start: datetime, end: datetime, reason: str) -> list[RawItem]:
        """Expected public rate limiting is a degraded source state, not a crash.

        This keeps the run fast and preserves PARTIAL/source-health evidence without
        writing a traceback to error.log on every five-minute refresh.
        """
        cached_rows=self._rows_from_articles(self._load_cached_articles(),start,end,cached=True)
        if cached_rows:
            self.last_status=f"SUCCESS_CACHE_CIRCUIT:{len(cached_rows)};LIVE_ERROR={reason[:120]}"
            logger.warning("gdelt circuit/cache fallback | rows=%d | reason=%s",len(cached_rows),reason[:160])
            return cached_rows
        self.last_status=f"DEGRADED:CIRCUIT_OPEN_NO_CACHE:{reason[:140]}"
        logger.warning("gdelt circuit open without cache | reason=%s",reason[:180])
        return []

    def collect(self, start: datetime, end: datetime) -> list[RawItem]:
        blocked, blocked_reason=self._circuit_open()
        if blocked:
            return self._cached_or_degraded(start,end,f"PERSISTED_CIRCUIT:{blocked_reason or 'RATE_LIMIT'}")
        params = {
            "query": self.query, "mode":"ArtList", "format":"json", "maxrecords":self.max_records,
            "startdatetime": start.astimezone(timezone.utc).strftime("%Y%m%d%H%M%S"),
            "enddatetime": end.astimezone(timezone.utc).strftime("%Y%m%d%H%M%S"), "sort":"DateDesc",
        }
        attempts = max(1, int(os.getenv("GDELT_RETRIES", "1")))
        min_gap = max(5.2, float(os.getenv("GDELT_RETRY_SECONDS", "5.5")))
        last_error = ""
        for attempt in range(attempts):
            try:
                r = requests.get(self.endpoint, params=params, timeout=self.timeout, headers={"User-Agent":"TrumpEventMonitor/2.3.17"})
            except requests.RequestException as exc:
                last_error = f"GDELT 連線失敗: {type(exc).__name__}"
                if attempt + 1 < attempts:
                    time.sleep(min_gap)
                    continue
                # V2.3.17: timeout/transport failure from this public endpoint is an
                # expected degraded-source condition in five-minute monitoring.
                # Open the same persisted circuit used for 429 and avoid repeated
                # traceback spam/latency on subsequent runs.
                self._mark_circuit(last_error)
                return self._cached_or_degraded(start, end, last_error)

            body_preview = " ".join((getattr(r, "text", "") or "").split())[:180]
            if r.status_code == 200:
                try:
                    payload = r.json()
                except ValueError:
                    if self._looks_rate_limited(body_preview):
                        last_error = f"GDELT SOFT_RATE_LIMIT_HTTP_200:{body_preview}"
                    else:
                        ctype = str(r.headers.get("Content-Type", ""))
                        last_error = f"GDELT NON_JSON_HTTP_200:content_type={ctype};body={body_preview}"
                    logger.warning("gdelt non-json response | attempt=%d/%d | %s", attempt+1, attempts, last_error[:240])
                    if attempt + 1 < attempts:
                        time.sleep(min_gap * (attempt + 1))
                        continue
                    if self._looks_rate_limited(body_preview):
                        self._mark_circuit(last_error)
                        return self._cached_or_degraded(start,end,last_error)
                    return self._cached_or_raise(start, end, last_error)
                articles = payload.get("articles", []) if isinstance(payload, dict) else []
                if not isinstance(articles, list):
                    last_error = "GDELT JSON_SCHEMA_INVALID:articles_not_list"
                    if attempt + 1 < attempts:
                        time.sleep(min_gap)
                        continue
                    return self._cached_or_raise(start, end, last_error)
                self._save_cached_articles(articles)
                self.last_status = f"SUCCESS:{len(articles)}"
                return self._rows_from_articles(articles, start, end, cached=False)

            last_error = f"GDELT HTTP {r.status_code}: {body_preview}"
            if r.status_code == 429:
                if attempt + 1 < attempts:
                    retry_after = r.headers.get("Retry-After", "")
                    try:
                        wait = max(min_gap, float(retry_after)) if retry_after else min_gap * (attempt + 1)
                    except ValueError:
                        wait = min_gap * (attempt + 1)
                    time.sleep(min(wait, 30.0))
                    continue
                self._mark_circuit(last_error)
                return self._cached_or_degraded(start,end,last_error)
            if 500 <= r.status_code < 600 and attempt + 1 < attempts:
                time.sleep(min_gap)
                continue
            return self._cached_or_raise(start, end, last_error)

        return self._cached_or_raise(start, end, last_error)
