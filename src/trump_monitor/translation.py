from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
import json
import os
from pathlib import Path
import random
import re
import threading
import time
from typing import Iterable

import requests

from trump_monitor.logging_utils import get_logger

logger = get_logger("translation")

_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")
_CACHE: dict[str, "TranslationResult"] = {}
_CACHE_LOCK = threading.Lock()
_CACHE_LOADED = False
_RATE_LOCK = threading.Lock()
_LAST_REQUEST_AT = 0.0


@dataclass(frozen=True)
class TranslationResult:
    text_zh: str
    provider: str
    status: str


def contains_cjk(text: str) -> bool:
    return bool(_CJK_RE.search(text or ""))


def _enabled() -> bool:
    return os.getenv("TRANSLATION_ENABLED", "true").strip().lower() not in {"0", "false", "no", "off"}


def _provider() -> str:
    value = os.getenv("TRANSLATION_PROVIDER", "AUTO").strip().upper()
    if value not in {"AUTO", "LLM", "GOOGLE_WEB", "OFF"}:
        value = "AUTO"
    if value == "AUTO":
        if os.getenv("AI_API_URL", "").strip() and os.getenv("AI_API_KEY", "").strip() and os.getenv("AI_MODEL", "").strip():
            return "LLM"
        return "GOOGLE_WEB"
    return value


def _cache_path() -> Path:
    return Path(os.getenv("TRANSLATION_CACHE_PATH", "output/translation_cache.json"))


def _load_cache_once() -> None:
    global _CACHE_LOADED
    with _CACHE_LOCK:
        if _CACHE_LOADED:
            return
        _CACHE_LOADED = True
        p = _cache_path()
        try:
            if not p.exists():
                return
            data = json.loads(p.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return
            for text, rec in data.items():
                if not isinstance(rec, dict):
                    continue
                zh = str(rec.get("text_zh") or "").strip()
                if zh and contains_cjk(zh):
                    _CACHE[text] = TranslationResult(zh, str(rec.get("provider") or "CACHE"), "SUCCESS:CACHE")
        except Exception as exc:
            logger.warning("translation cache load failed | %s", type(exc).__name__)


def _persist_cache() -> None:
    p = _cache_path()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        with _CACHE_LOCK:
            data = {k: {"text_zh": v.text_zh, "provider": v.provider} for k, v in _CACHE.items() if v.text_zh and contains_cjk(v.text_zh)}
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(p)
    except Exception as exc:
        logger.warning("translation cache persist failed | %s", type(exc).__name__)


def _throttle() -> None:
    global _LAST_REQUEST_AT
    delay = max(0.0, float(os.getenv("TRANSLATION_RATE_LIMIT_SECONDS", "0.35")))
    if delay <= 0:
        return
    with _RATE_LOCK:
        now = time.monotonic()
        wait = delay - (now - _LAST_REQUEST_AT)
        if wait > 0:
            time.sleep(wait)
        _LAST_REQUEST_AT = time.monotonic()


def _validate_translation(text: str, translated: str, provider: str) -> TranslationResult:
    clean = (translated or "").strip()
    if not clean:
        return TranslationResult("", provider, "EMPTY")
    if not contains_cjk(text) and not contains_cjk(clean):
        return TranslationResult("", provider, "INVALID_NO_CJK")
    return TranslationResult(clean, provider, "SUCCESS")


def _translate_llm(text: str) -> TranslationResult:
    url = os.getenv("AI_API_URL", "").strip()
    key = os.getenv("AI_API_KEY", "").strip()
    model = os.getenv("AI_MODEL", "").strip()
    if not (url and key and model):
        return TranslationResult("", "LLM", "NOT_CONFIGURED")
    timeout = float(os.getenv("TRANSLATION_TIMEOUT_SECONDS", "12"))
    payload = {
        "model": model,
        "messages": [{
            "role": "user",
            "content": "Translate the following public-news headline to Traditional Chinese (Taiwan). Preserve names, tickers, numbers and source/publisher names exactly. Return translation only.\n\n" + text,
        }],
        "temperature": 0,
    }
    r = requests.post(url, headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"}, json=payload, timeout=timeout)
    r.raise_for_status()
    translated = str(r.json()["choices"][0]["message"]["content"]).strip()
    return _validate_translation(text, translated, f"LLM:{model}")


def _translate_google_web(text: str) -> TranslationResult:
    configured = os.getenv("TRANSLATION_API_URL", "").strip()
    endpoints = [configured] if configured else [
        "https://translate.googleapis.com/translate_a/single",
        "https://translate.google.com/translate_a/single",
    ]
    timeout = float(os.getenv("TRANSLATION_TIMEOUT_SECONDS", "10"))
    attempts = max(1, int(os.getenv("TRANSLATION_RETRIES", "3")))
    last_status = "FAILED:UNKNOWN"
    for attempt in range(attempts):
        for endpoint in endpoints:
            try:
                _throttle()
                r = requests.get(endpoint, params={"client": "gtx", "sl": "auto", "tl": "zh-TW", "dt": "t", "q": text}, timeout=timeout, headers={"User-Agent": "Mozilla/5.0 TrumpEventMonitor/2.3.11"})
                status_code = int(getattr(r, "status_code", 200))
                if status_code == 429 or 500 <= status_code < 600:
                    last_status = f"FAILED:HTTP_{status_code}"
                    retry_after = r.headers.get("Retry-After", "")
                    try:
                        base_wait = float(retry_after) if retry_after else (0.8 * (2 ** attempt))
                    except ValueError:
                        base_wait = 0.8 * (2 ** attempt)
                    time.sleep(min(base_wait + random.uniform(0, 0.25), 6.0))
                    continue
                r.raise_for_status()
                data = r.json()
                segments = data[0] if isinstance(data, list) and data else []
                translated = "".join(str(seg[0]) for seg in segments if isinstance(seg, list) and seg and seg[0]).strip()
                result = _validate_translation(text, translated, "GOOGLE_WEB_UNOFFICIAL")
                if result.text_zh:
                    return result
                last_status = result.status
            except requests.HTTPError as exc:
                code = getattr(exc.response, "status_code", None)
                last_status = f"FAILED:HTTP_{code}" if code else "FAILED:HTTP_ERROR"
            except requests.Timeout:
                last_status = "FAILED:TIMEOUT"
            except requests.RequestException as exc:
                last_status = f"FAILED:{type(exc).__name__}"
            except ValueError:
                last_status = "FAILED:INVALID_JSON"
        if attempt + 1 < attempts:
            time.sleep(min(0.5 * (2 ** attempt), 3.0))
    return TranslationResult("", "GOOGLE_WEB_UNOFFICIAL", last_status)



def _parse_google_payload(data) -> str:
    segments = data[0] if isinstance(data, list) and data else []
    return "".join(str(seg[0]) for seg in segments if isinstance(seg, list) and seg and seg[0]).strip()


def _translate_google_web_batch(texts: list[str]) -> dict[str, TranslationResult]:
    """Translate several headlines in one request to reduce 429 burst failures.

    The Google Web endpoint is unofficial and rate-limited.  V2.3.11 issued one
    request per title, which still produced an all-429 live run.  V2.3.12 sends
    small marker-delimited batches, validates every translated segment, and
    falls back to per-title retry only when a batch cannot be parsed.
    """
    if not texts:
        return {}
    configured = os.getenv("TRANSLATION_API_URL", "").strip()
    endpoints = [configured] if configured else [
        "https://translate.googleapis.com/translate_a/single",
        "https://translate.google.com/translate_a/single",
    ]
    timeout = float(os.getenv("TRANSLATION_TIMEOUT_SECONDS", "12"))
    attempts = max(1, int(os.getenv("TRANSLATION_RETRIES", "3")))
    marker_prefix = "TMEISSEG"
    joined = "\n".join(f"[[{marker_prefix}{idx:03d}]] {text}" for idx, text in enumerate(texts))
    last_status = "FAILED:UNKNOWN"
    for attempt in range(attempts):
        for endpoint in endpoints:
            try:
                _throttle()
                r = requests.get(endpoint, params={"client":"gtx","sl":"auto","tl":"zh-TW","dt":"t","q":joined}, timeout=timeout, headers={"User-Agent":"Mozilla/5.0 TrumpEventMonitor/2.3.12"})
                code = int(getattr(r, "status_code", 200))
                if code == 429 or 500 <= code < 600:
                    last_status = f"FAILED:HTTP_{code}"
                    retry_after = r.headers.get("Retry-After", "")
                    try:
                        wait = float(retry_after) if retry_after else max(1.5, 1.5 * (2 ** attempt))
                    except ValueError:
                        wait = max(1.5, 1.5 * (2 ** attempt))
                    time.sleep(min(wait + random.uniform(0, .25), 8.0))
                    continue
                r.raise_for_status()
                translated = _parse_google_payload(r.json())
                # Markers are ASCII and normally preserved verbatim by the endpoint.
                pat = re.compile(r"\[\[" + marker_prefix + r"(\d{3})\]\]\s*")
                matches = list(pat.finditer(translated))
                if len(matches) != len(texts):
                    last_status = "FAILED:BATCH_MARKER_PARSE"
                    continue
                out: dict[str, TranslationResult] = {}
                for pos, m in enumerate(matches):
                    idx = int(m.group(1))
                    end = matches[pos + 1].start() if pos + 1 < len(matches) else len(translated)
                    value = translated[m.end():end].strip()
                    out[texts[idx]] = _validate_translation(texts[idx], value, "GOOGLE_WEB_BATCH_UNOFFICIAL")
                if all(t in out for t in texts):
                    return out
                last_status = "FAILED:BATCH_INCOMPLETE"
            except requests.HTTPError as exc:
                code = getattr(exc.response, "status_code", None)
                last_status = f"FAILED:HTTP_{code}" if code else "FAILED:HTTP_ERROR"
            except requests.Timeout:
                last_status = "FAILED:TIMEOUT"
            except requests.RequestException as exc:
                last_status = f"FAILED:{type(exc).__name__}"
            except ValueError:
                last_status = "FAILED:INVALID_JSON"
        if attempt + 1 < attempts:
            time.sleep(min(1.0 * (2 ** attempt), 5.0))
    return {t: TranslationResult("", "GOOGLE_WEB_BATCH_UNOFFICIAL", last_status) for t in texts}

def translate_text(text: str) -> TranslationResult:
    clean = " ".join((text or "").split()).strip()
    if not clean:
        return TranslationResult("", "NONE", "EMPTY_INPUT")
    if contains_cjk(clean):
        return TranslationResult(clean, "NONE", "ALREADY_ZH")
    if not _enabled() or _provider() == "OFF":
        return TranslationResult("", "NONE", "DISABLED")
    _load_cache_once()
    with _CACHE_LOCK:
        cached = _CACHE.get(clean)
    if cached is not None:
        return cached
    provider = _provider()
    try:
        result = _translate_llm(clean) if provider == "LLM" else _translate_google_web(clean)
    except Exception as exc:
        logger.warning("translation failed | provider=%s | error=%s | text=%s", provider, type(exc).__name__, clean[:120])
        result = TranslationResult("", provider, f"FAILED:{type(exc).__name__}")
    # Only successful, actually-Chinese results are cached. Failed calls are retried on later runs.
    if result.text_zh and contains_cjk(result.text_zh):
        with _CACHE_LOCK:
            _CACHE[clean] = result
        _persist_cache()
    else:
        logger.warning("translation unavailable | provider=%s | status=%s | text=%s", result.provider, result.status, clean[:120])
    return result


def translate_many(texts: Iterable[str], max_workers: int | None = None) -> dict[str, TranslationResult]:
    unique = list(dict.fromkeys(" ".join((t or "").split()).strip() for t in texts if (t or "").strip()))
    if not unique:
        return {}
    _load_cache_once()
    results: dict[str, TranslationResult] = {}
    pending: list[str] = []
    for text in unique:
        if contains_cjk(text):
            results[text] = TranslationResult(text, "NONE", "ALREADY_ZH")
            continue
        with _CACHE_LOCK:
            cached = _CACHE.get(text)
        if cached is not None:
            results[text] = cached
        else:
            pending.append(text)

    provider = _provider()
    if not _enabled() or provider == "OFF":
        for text in pending:
            results[text] = TranslationResult("", "NONE", "DISABLED")
    elif provider == "GOOGLE_WEB":
        batch_size = max(2, min(12, int(os.getenv("TRANSLATION_BATCH_SIZE", "8"))))
        for i in range(0, len(pending), batch_size):
            batch = pending[i:i+batch_size]
            batch_results = _translate_google_web_batch(batch)
            results.update(batch_results)
            # Only successful Chinese results enter persistent cache.
            for text, result in batch_results.items():
                if result.text_zh and contains_cjk(result.text_zh):
                    with _CACHE_LOCK:
                        _CACHE[text] = result
            if i + batch_size < len(pending):
                time.sleep(max(0.0, float(os.getenv("TRANSLATION_BATCH_PAUSE_SECONDS", "1.5"))))
        _persist_cache()
    else:
        workers = max(1, int(max_workers or os.getenv("TRANSLATION_MAX_WORKERS", "2")))
        workers = min(workers, 4, len(pending) or 1)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(translate_text, text): text for text in pending}
            for future in as_completed(futures):
                text = futures[future]
                try:
                    results[text] = future.result()
                except Exception as exc:
                    results[text] = TranslationResult("", provider, f"FAILED:{type(exc).__name__}")

    success = sum(1 for r in results.values() if r.text_zh)
    failed = len(unique) - success
    logger.info("translation batch | requested=%d | success=%d | failed=%d | provider=%s | batch_size=%s", len(unique), success, failed, provider, os.getenv("TRANSLATION_BATCH_SIZE", "8"))
    return results
