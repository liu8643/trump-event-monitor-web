from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
import os
import re
import threading
from typing import Iterable

import requests

from trump_monitor.logging_utils import get_logger

logger = get_logger("translation")

_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")
_CACHE: dict[str, "TranslationResult"] = {}
_CACHE_LOCK = threading.Lock()


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


def _translate_llm(text: str) -> TranslationResult:
    url = os.getenv("AI_API_URL", "").strip()
    key = os.getenv("AI_API_KEY", "").strip()
    model = os.getenv("AI_MODEL", "").strip()
    if not (url and key and model):
        return TranslationResult("", "LLM", "NOT_CONFIGURED")
    timeout = float(os.getenv("TRANSLATION_TIMEOUT_SECONDS", "10"))
    payload = {
        "model": model,
        "messages": [{
            "role": "user",
            "content": "Translate the following public-news text to Traditional Chinese (Taiwan). Preserve names, tickers and numbers. Return translation only.\n\n" + text,
        }],
        "temperature": 0,
    }
    r = requests.post(url, headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"}, json=payload, timeout=timeout)
    r.raise_for_status()
    translated = str(r.json()["choices"][0]["message"]["content"]).strip()
    return TranslationResult(translated, f"LLM:{model}", "SUCCESS" if translated else "EMPTY")


def _translate_google_web(text: str) -> TranslationResult:
    configured = os.getenv("TRANSLATION_API_URL", "").strip()
    endpoints = [configured] if configured else [
        "https://translate.googleapis.com/translate_a/single",
        "https://translate.google.com/translate_a/single",
    ]
    timeout = float(os.getenv("TRANSLATION_TIMEOUT_SECONDS", "8"))
    last_exc: Exception | None = None
    for endpoint in endpoints:
        try:
            r = requests.get(endpoint, params={"client": "gtx", "sl": "auto", "tl": "zh-TW", "dt": "t", "q": text}, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"})
            r.raise_for_status()
            data = r.json()
            segments = data[0] if isinstance(data, list) and data else []
            translated = "".join(str(seg[0]) for seg in segments if isinstance(seg, list) and seg and seg[0]).strip()
            if translated:
                return TranslationResult(translated, "GOOGLE_WEB_UNOFFICIAL", "SUCCESS")
        except Exception as exc:
            last_exc = exc
    if last_exc:
        raise last_exc
    return TranslationResult("", "GOOGLE_WEB_UNOFFICIAL", "EMPTY")


def translate_text(text: str) -> TranslationResult:
    clean = " ".join((text or "").split()).strip()
    if not clean:
        return TranslationResult("", "NONE", "EMPTY_INPUT")
    if contains_cjk(clean):
        return TranslationResult(clean, "NONE", "ALREADY_ZH")
    if not _enabled() or _provider() == "OFF":
        return TranslationResult("", "NONE", "DISABLED")
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
    with _CACHE_LOCK:
        _CACHE[clean] = result
    return result


def translate_many(texts: Iterable[str], max_workers: int | None = None) -> dict[str, TranslationResult]:
    unique = list(dict.fromkeys(" ".join((t or "").split()).strip() for t in texts if (t or "").strip()))
    if not unique:
        return {}
    workers = max(1, int(max_workers or os.getenv("TRANSLATION_MAX_WORKERS", "8")))
    workers = min(workers, 12, len(unique))
    results: dict[str, TranslationResult] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(translate_text, text): text for text in unique}
        for future in as_completed(futures):
            text = futures[future]
            try:
                results[text] = future.result()
            except Exception as exc:  # defensive: translate_text already catches provider errors
                results[text] = TranslationResult("", _provider(), f"FAILED:{type(exc).__name__}")
    success = sum(1 for r in results.values() if r.text_zh)
    logger.info("translation batch | requested=%d | success=%d | provider=%s", len(unique), success, _provider())
    return results
