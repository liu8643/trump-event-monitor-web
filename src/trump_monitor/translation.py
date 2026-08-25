from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
import html
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
_GOOGLE_BLOCKED_UNTIL = 0.0
_MYMEMORY_BLOCKED_UNTIL = 0.0


@dataclass(frozen=True)
class TranslationResult:
    text_zh: str
    provider: str
    status: str


def contains_cjk(text: str) -> bool:
    return bool(_CJK_RE.search(text or ""))


def normalize_zh_tw(text: str) -> str:
    """Conservative Taiwan-facing terminology normalization.

    Public fallback providers can return valid Traditional Chinese while still
    using non-Taiwan political naming (for example 特朗普).  Keep this mapping
    deliberately narrow so it never rewrites publisher names, tickers, numbers,
    or the English evidence layer.
    """
    value = html.unescape((text or "").strip())
    replacements = {
        "特朗普": "川普",
        "唐納德·特朗普": "唐納·川普",
        "唐納德特朗普": "唐納·川普",
    }
    for src, dst in replacements.items():
        value = value.replace(src, dst)
    return value


def _enabled() -> bool:
    return os.getenv("TRANSLATION_ENABLED", "true").strip().lower() not in {"0", "false", "no", "off"}


def _provider() -> str:
    value = os.getenv("TRANSLATION_PROVIDER", "AUTO").strip().upper()
    if value not in {"AUTO", "LLM", "GOOGLE_WEB", "MYMEMORY", "OFF"}:
        value = "AUTO"
    if value == "AUTO":
        if os.getenv("AI_API_URL", "").strip() and os.getenv("AI_API_KEY", "").strip() and os.getenv("AI_MODEL", "").strip():
            return "LLM"
        return "GOOGLE_WEB"
    return value


def _fallback_provider() -> str:
    value = os.getenv("TRANSLATION_FALLBACK_PROVIDER", "MYMEMORY").strip().upper()
    return value if value in {"MYMEMORY", "OFF"} else "MYMEMORY"


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


def _throttle(delay_env: str = "TRANSLATION_RATE_LIMIT_SECONDS", default: str = "0.35") -> None:
    global _LAST_REQUEST_AT
    delay = max(0.0, float(os.getenv(delay_env, default)))
    if delay <= 0:
        return
    with _RATE_LOCK:
        now = time.monotonic()
        wait = delay - (now - _LAST_REQUEST_AT)
        if wait > 0:
            time.sleep(wait)
        _LAST_REQUEST_AT = time.monotonic()


def _validate_translation(text: str, translated: str, provider: str) -> TranslationResult:
    clean = normalize_zh_tw(translated)
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


def _parse_google_payload(data) -> str:
    segments = data[0] if isinstance(data, list) and data else []
    return "".join(str(seg[0]) for seg in segments if isinstance(seg, list) and seg and seg[0]).strip()


def _mark_google_blocked(seconds: float | None = None) -> None:
    global _GOOGLE_BLOCKED_UNTIL
    seconds = seconds if seconds is not None else float(os.getenv("TRANSLATION_GOOGLE_CIRCUIT_SECONDS", "900"))
    _GOOGLE_BLOCKED_UNTIL = max(_GOOGLE_BLOCKED_UNTIL, time.monotonic() + max(30.0, seconds))


def _google_circuit_open() -> bool:
    return time.monotonic() < _GOOGLE_BLOCKED_UNTIL


def _translate_google_web(text: str) -> TranslationResult:
    if _google_circuit_open():
        return TranslationResult("", "GOOGLE_WEB_UNOFFICIAL", "FAILED:CIRCUIT_OPEN")
    configured = os.getenv("TRANSLATION_API_URL", "").strip()
    endpoints = [configured] if configured else [
        "https://translate.googleapis.com/translate_a/single",
        "https://translate.google.com/translate_a/single",
    ]
    timeout = float(os.getenv("TRANSLATION_TIMEOUT_SECONDS", "10"))
    attempts = max(1, int(os.getenv("TRANSLATION_RETRIES", "2")))
    last_status = "FAILED:UNKNOWN"
    for attempt in range(attempts):
        for endpoint in endpoints:
            try:
                _throttle()
                r = requests.get(endpoint, params={"client": "gtx", "sl": "auto", "tl": "zh-TW", "dt": "t", "q": text}, timeout=timeout, headers={"User-Agent": "Mozilla/5.0 TrumpEventMonitor/2.3.15"})
                status_code = int(getattr(r, "status_code", 200))
                if status_code == 429:
                    _mark_google_blocked()
                    return TranslationResult("", "GOOGLE_WEB_UNOFFICIAL", "FAILED:HTTP_429:CIRCUIT_OPEN")
                if 500 <= status_code < 600:
                    last_status = f"FAILED:HTTP_{status_code}"
                    continue
                r.raise_for_status()
                result = _validate_translation(text, _parse_google_payload(r.json()), "GOOGLE_WEB_UNOFFICIAL")
                if result.text_zh:
                    return result
                last_status = result.status
            except requests.HTTPError as exc:
                code = getattr(exc.response, "status_code", None)
                if code == 429:
                    _mark_google_blocked()
                    return TranslationResult("", "GOOGLE_WEB_UNOFFICIAL", "FAILED:HTTP_429:CIRCUIT_OPEN")
                last_status = f"FAILED:HTTP_{code}" if code else "FAILED:HTTP_ERROR"
            except requests.Timeout:
                last_status = "FAILED:TIMEOUT"
            except requests.RequestException as exc:
                last_status = f"FAILED:{type(exc).__name__}"
            except ValueError:
                last_status = "FAILED:INVALID_JSON"
        if attempt + 1 < attempts:
            time.sleep(min(0.75 * (2 ** attempt), 2.0))
    return TranslationResult("", "GOOGLE_WEB_UNOFFICIAL", last_status)


def _translate_google_web_batch(texts: list[str]) -> dict[str, TranslationResult]:
    if not texts:
        return {}
    if _google_circuit_open():
        return {t: TranslationResult("", "GOOGLE_WEB_BATCH_UNOFFICIAL", "FAILED:CIRCUIT_OPEN") for t in texts}
    configured = os.getenv("TRANSLATION_API_URL", "").strip()
    endpoints = [configured] if configured else [
        "https://translate.googleapis.com/translate_a/single",
        "https://translate.google.com/translate_a/single",
    ]
    timeout = float(os.getenv("TRANSLATION_TIMEOUT_SECONDS", "12"))
    attempts = max(1, int(os.getenv("TRANSLATION_RETRIES", "2")))
    marker_prefix = "TMEISSEG"
    joined = "\n".join(f"[[{marker_prefix}{idx:03d}]] {text}" for idx, text in enumerate(texts))
    last_status = "FAILED:UNKNOWN"
    for attempt in range(attempts):
        for endpoint in endpoints:
            try:
                _throttle()
                r = requests.get(endpoint, params={"client":"gtx","sl":"auto","tl":"zh-TW","dt":"t","q":joined}, timeout=timeout, headers={"User-Agent":"Mozilla/5.0 TrumpEventMonitor/2.3.15"})
                code = int(getattr(r, "status_code", 200))
                if code == 429:
                    _mark_google_blocked()
                    status = "FAILED:HTTP_429:CIRCUIT_OPEN"
                    logger.warning("translation google circuit opened | status=%s | batch=%d", status, len(texts))
                    return {t: TranslationResult("", "GOOGLE_WEB_BATCH_UNOFFICIAL", status) for t in texts}
                if 500 <= code < 600:
                    last_status = f"FAILED:HTTP_{code}"
                    continue
                r.raise_for_status()
                translated = _parse_google_payload(r.json())
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
                if code == 429:
                    _mark_google_blocked()
                    status = "FAILED:HTTP_429:CIRCUIT_OPEN"
                    return {t: TranslationResult("", "GOOGLE_WEB_BATCH_UNOFFICIAL", status) for t in texts}
                last_status = f"FAILED:HTTP_{code}" if code else "FAILED:HTTP_ERROR"
            except requests.Timeout:
                last_status = "FAILED:TIMEOUT"
            except requests.RequestException as exc:
                last_status = f"FAILED:{type(exc).__name__}"
            except ValueError:
                last_status = "FAILED:INVALID_JSON"
        if attempt + 1 < attempts:
            time.sleep(min(0.75 * (2 ** attempt), 2.0))
    return {t: TranslationResult("", "GOOGLE_WEB_BATCH_UNOFFICIAL", last_status) for t in texts}


def _mark_mymemory_blocked(seconds: float = 600.0) -> None:
    global _MYMEMORY_BLOCKED_UNTIL
    _MYMEMORY_BLOCKED_UNTIL = max(_MYMEMORY_BLOCKED_UNTIL, time.monotonic() + max(30.0, seconds))


def _mymemory_circuit_open() -> bool:
    return time.monotonic() < _MYMEMORY_BLOCKED_UNTIL


def _pack_texts(texts: list[str], max_items: int, max_chars: int) -> list[list[str]]:
    packs: list[list[str]] = []
    current: list[str] = []
    chars = 0
    for text in texts:
        extra = len(text) + 24
        if current and (len(current) >= max_items or chars + extra > max_chars):
            packs.append(current); current=[]; chars=0
        current.append(text); chars += extra
    if current:
        packs.append(current)
    return packs


def _translate_mymemory_batch(texts: list[str]) -> dict[str, TranslationResult]:
    """Best-effort second public provider used only after Google Web is blocked.

    MyMemory is a public translation-memory API, not a licensed enterprise SLA.
    Results are still validated for CJK and clearly labeled in evidence fields.
    """
    if not texts:
        return {}
    if _mymemory_circuit_open():
        return {t: TranslationResult("", "MYMEMORY_PUBLIC", "FAILED:CIRCUIT_OPEN") for t in texts}
    endpoint = os.getenv("MYMEMORY_API_URL", "https://api.mymemory.translated.net/get").strip()
    marker_prefix = "MMEISSEG"
    joined = "\n".join(f"[[{marker_prefix}{idx:03d}]] {text}" for idx, text in enumerate(texts))
    params = {"q": joined, "langpair": "en|zh-TW"}
    email = os.getenv("MYMEMORY_EMAIL", "").strip()
    if email:
        params["de"] = email
    try:
        _throttle("TRANSLATION_MYMEMORY_RATE_LIMIT_SECONDS", "0.8")
        r = requests.get(endpoint, params=params, timeout=float(os.getenv("TRANSLATION_TIMEOUT_SECONDS", "12")), headers={"User-Agent":"TrumpEventMonitor/2.3.15"})
        code = int(getattr(r, "status_code", 200))
        if code == 429:
            _mark_mymemory_blocked()
            return {t: TranslationResult("", "MYMEMORY_PUBLIC", "FAILED:HTTP_429:CIRCUIT_OPEN") for t in texts}
        r.raise_for_status()
        payload = r.json()
        translated = html.unescape(str((payload.get("responseData") or {}).get("translatedText") or "")).strip() if isinstance(payload, dict) else ""
        pat = re.compile(r"\[\[" + marker_prefix + r"(\d{3})\]\]\s*")
        matches = list(pat.finditer(translated))
        if len(texts) == 1 and not matches:
            return {texts[0]: _validate_translation(texts[0], translated, "MYMEMORY_PUBLIC")}
        if len(matches) != len(texts):
            return {t: TranslationResult("", "MYMEMORY_PUBLIC", "FAILED:BATCH_MARKER_PARSE") for t in texts}
        out: dict[str, TranslationResult] = {}
        for pos, m in enumerate(matches):
            idx = int(m.group(1))
            end = matches[pos+1].start() if pos+1 < len(matches) else len(translated)
            out[texts[idx]] = _validate_translation(texts[idx], translated[m.end():end].strip(), "MYMEMORY_PUBLIC")
        return out
    except requests.Timeout:
        return {t: TranslationResult("", "MYMEMORY_PUBLIC", "FAILED:TIMEOUT") for t in texts}
    except requests.HTTPError as exc:
        code = getattr(exc.response, "status_code", None)
        return {t: TranslationResult("", "MYMEMORY_PUBLIC", f"FAILED:HTTP_{code}" if code else "FAILED:HTTP_ERROR") for t in texts}
    except requests.RequestException as exc:
        return {t: TranslationResult("", "MYMEMORY_PUBLIC", f"FAILED:{type(exc).__name__}") for t in texts}
    except ValueError:
        return {t: TranslationResult("", "MYMEMORY_PUBLIC", "FAILED:INVALID_JSON") for t in texts}


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
        if provider == "LLM":
            result = _translate_llm(clean)
        elif provider == "MYMEMORY":
            result = _translate_mymemory_batch([clean])[clean]
        else:
            result = _translate_google_web(clean)
            if not result.text_zh and _fallback_provider() == "MYMEMORY":
                fallback = _translate_mymemory_batch([clean])[clean]
                if fallback.text_zh:
                    result = fallback
                else:
                    result = TranslationResult("", fallback.provider, f"PRIMARY:{result.status};FALLBACK:{fallback.status}")
    except Exception as exc:
        logger.warning("translation failed | provider=%s | error=%s | text=%s", provider, type(exc).__name__, clean[:120])
        result = TranslationResult("", provider, f"FAILED:{type(exc).__name__}")
    if result.text_zh and contains_cjk(result.text_zh):
        with _CACHE_LOCK:
            _CACHE[clean] = result
        _persist_cache()
    else:
        logger.warning("translation unavailable | provider=%s | status=%s | text=%s", result.provider, result.status, clean[:120])
    return result


def translate_many(texts: Iterable[str], max_workers: int | None = None) -> dict[str, TranslationResult]:
    started = time.monotonic()
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
        google_failed: list[str] = []
        for i in range(0, len(pending), batch_size):
            batch = pending[i:i+batch_size]
            batch_results = _translate_google_web_batch(batch)
            results.update(batch_results)
            for text, result in batch_results.items():
                if result.text_zh and contains_cjk(result.text_zh):
                    with _CACHE_LOCK:
                        _CACHE[text] = result
                else:
                    google_failed.append(text)
            # Once 429 opens the circuit, do not waste minutes retrying the same provider for every batch.
            if _google_circuit_open():
                remaining = pending[i+batch_size:]
                google_failed.extend(remaining)
                for text in remaining:
                    results[text] = TranslationResult("", "GOOGLE_WEB_BATCH_UNOFFICIAL", "FAILED:CIRCUIT_OPEN")
                break
            if i + batch_size < len(pending):
                time.sleep(max(0.0, float(os.getenv("TRANSLATION_BATCH_PAUSE_SECONDS", "1.0"))))

        if google_failed and _fallback_provider() == "MYMEMORY":
            # Public fallback uses smaller character-bounded batches because the API query limit is tighter.
            max_items = max(1, min(4, int(os.getenv("TRANSLATION_MYMEMORY_BATCH_SIZE", "3"))))
            max_chars = max(180, int(os.getenv("TRANSLATION_MYMEMORY_MAX_CHARS", "420")))
            for pack in _pack_texts(list(dict.fromkeys(google_failed)), max_items, max_chars):
                fb = _translate_mymemory_batch(pack)
                for text, res in fb.items():
                    if res.text_zh:
                        results[text] = res
                        with _CACHE_LOCK:
                            _CACHE[text] = res
                    else:
                        primary = results.get(text)
                        primary_status = primary.status if primary else "NOT_RUN"
                        results[text] = TranslationResult("", res.provider, f"PRIMARY:{primary_status};FALLBACK:{res.status}")
                if _mymemory_circuit_open():
                    break
        _persist_cache()
    elif provider == "MYMEMORY":
        for pack in _pack_texts(pending, max(1, min(4, int(os.getenv("TRANSLATION_MYMEMORY_BATCH_SIZE", "3")))), max(180, int(os.getenv("TRANSLATION_MYMEMORY_MAX_CHARS", "420")))):
            batch_results = _translate_mymemory_batch(pack)
            results.update(batch_results)
            for text, result in batch_results.items():
                if result.text_zh:
                    with _CACHE_LOCK:
                        _CACHE[text] = result
            if _mymemory_circuit_open():
                break
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

    # Ensure every requested string has an explicit result even if a fallback circuit opened mid-run.
    for text in unique:
        results.setdefault(text, TranslationResult("", provider, "FAILED:NOT_ATTEMPTED"))
    success = sum(1 for r in results.values() if r.text_zh)
    failed = len(unique) - success
    provider_counts: dict[str, int] = {}
    for r in results.values():
        provider_counts[r.provider] = provider_counts.get(r.provider, 0) + 1
    effective = ",".join(f"{k}:{v}" for k,v in sorted(provider_counts.items())) or "NONE"
    logger.info("translation batch | requested=%d | success=%d | failed=%d | primary_provider=%s | effective_providers=%s | elapsed=%.2fs", len(unique), success, failed, provider, effective, time.monotonic()-started)
    return results
