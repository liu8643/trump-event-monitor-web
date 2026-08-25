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
_LINGVA_BLOCKED_UNTIL = 0.0


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


def _fallback_providers() -> list[str]:
    """Ordered public fallbacks.

    V2.3.18 retains a second no-key provider after MyMemory so one public-service
    quota does not erase all Chinese output.  Values are always evidence-labeled.
    """
    raw = os.getenv("TRANSLATION_FALLBACK_PROVIDER", "MYMEMORY,LINGVA").strip().upper()
    if raw in {"", "OFF", "NONE"}:
        return []
    out=[]
    for value in re.split(r"[,;| ]+", raw):
        value=value.strip()
        if value in {"MYMEMORY", "LINGVA"} and value not in out:
            out.append(value)
    return out or ["MYMEMORY", "LINGVA"]


def _fallback_provider() -> str:
    providers=_fallback_providers()
    return providers[0] if providers else "OFF"


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
                r = requests.get(endpoint, params={"client": "gtx", "sl": "auto", "tl": "zh-TW", "dt": "t", "q": text}, timeout=timeout, headers={"User-Agent": "Mozilla/5.0 TrumpEventMonitor/2.3.18"})
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
                r = requests.get(endpoint, params={"client":"gtx","sl":"auto","tl":"zh-TW","dt":"t","q":joined}, timeout=timeout, headers={"User-Agent":"Mozilla/5.0 TrumpEventMonitor/2.3.18"})
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
        r = requests.get(endpoint, params=params, timeout=float(os.getenv("TRANSLATION_TIMEOUT_SECONDS", "12")), headers={"User-Agent":"TrumpEventMonitor/2.3.18"})
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


def _mark_lingva_blocked(seconds: float = 600.0) -> None:
    global _LINGVA_BLOCKED_UNTIL
    _LINGVA_BLOCKED_UNTIL = max(_LINGVA_BLOCKED_UNTIL, time.monotonic() + max(30.0, seconds))


def _lingva_circuit_open() -> bool:
    return time.monotonic() < _LINGVA_BLOCKED_UNTIL


def _lingva_instances() -> list[str]:
    raw=os.getenv("LINGVA_INSTANCES", "https://lingva.ml,https://translate.plausibility.cloud").strip()
    return [x.strip().rstrip("/") for x in raw.split(",") if x.strip()]


def _translate_lingva_batch(texts: list[str]) -> dict[str, TranslationResult]:
    """Third public fallback using Lingva's documented REST API.

    Headlines are public information.  The provider is explicitly identified as
    PUBLIC and is never treated as a licensed/first-party evidence source.
    """
    from urllib.parse import quote
    if not texts:
        return {}
    if _lingva_circuit_open():
        return {t: TranslationResult("", "LINGVA_PUBLIC", "FAILED:CIRCUIT_OPEN") for t in texts}
    marker_prefix="LGEISSEG"
    joined="\n".join(f"[[{marker_prefix}{idx:03d}]] {text}" for idx,text in enumerate(texts))
    timeout=float(os.getenv("TRANSLATION_TIMEOUT_SECONDS", "12"))
    last="FAILED:NO_INSTANCE"
    for base in _lingva_instances():
        try:
            _throttle("TRANSLATION_LINGVA_RATE_LIMIT_SECONDS", "0.7")
            url=f"{base}/api/v1/en/zh/{quote(joined, safe='')}"
            r=requests.get(url, timeout=timeout, headers={"User-Agent":"TrumpEventMonitor/2.3.18"})
            code=int(getattr(r,"status_code",200))
            if code==429:
                last="FAILED:HTTP_429"
                continue
            r.raise_for_status()
            payload=r.json()
            translated=html.unescape(str(payload.get("translation") or "")).strip() if isinstance(payload,dict) else ""
            pat=re.compile(r"\[\["+marker_prefix+r"(\d{3})\]\]\s*")
            matches=list(pat.finditer(translated))
            if len(texts)==1 and not matches:
                return {texts[0]: _validate_translation(texts[0],translated,"LINGVA_PUBLIC")}
            if len(matches)!=len(texts):
                last="FAILED:BATCH_MARKER_PARSE"
                continue
            out={}
            for pos,m in enumerate(matches):
                idx=int(m.group(1)); end=matches[pos+1].start() if pos+1<len(matches) else len(translated)
                out[texts[idx]]=_validate_translation(texts[idx],translated[m.end():end].strip(),"LINGVA_PUBLIC")
            if any(v.text_zh for v in out.values()):
                return out
            last="FAILED:NO_VALID_TRANSLATION"
        except requests.Timeout:
            last="FAILED:TIMEOUT"
        except requests.HTTPError as exc:
            code=getattr(exc.response,"status_code",None); last=f"FAILED:HTTP_{code}" if code else "FAILED:HTTP_ERROR"
        except requests.RequestException as exc:
            last=f"FAILED:{type(exc).__name__}"
        except ValueError:
            last="FAILED:INVALID_JSON"
    _mark_lingva_blocked(float(os.getenv("TRANSLATION_LINGVA_CIRCUIT_SECONDS","600")))
    return {t: TranslationResult("", "LINGVA_PUBLIC", last+":CIRCUIT_OPEN") for t in texts}


def _fallback_pending(texts: list[str], results: dict[str, TranslationResult]) -> None:
    """Run ordered public fallback providers and preserve full status evidence."""
    remaining=list(dict.fromkeys(texts))
    for provider in _fallback_providers():
        if not remaining:
            return
        next_remaining=[]
        if provider=="MYMEMORY":
            max_items=max(1,min(3,int(os.getenv("TRANSLATION_MYMEMORY_BATCH_SIZE","2"))))
            max_chars=max(180,int(os.getenv("TRANSLATION_MYMEMORY_MAX_CHARS","320")))
            packs=_pack_texts(remaining,max_items,max_chars)
            for pack in packs:
                fb=_translate_mymemory_batch(pack)
                for text in pack:
                    res=fb.get(text,TranslationResult("","MYMEMORY_PUBLIC","FAILED:NOT_RETURNED"))
                    if res.text_zh:
                        results[text]=res
                        with _CACHE_LOCK: _CACHE[text]=res
                    else:
                        prior=results.get(text); prior_status=prior.status if prior else "NOT_RUN"
                        results[text]=TranslationResult("",res.provider,f"PRIMARY:{prior_status};FALLBACK:{res.status}")
                        next_remaining.append(text)
                if _mymemory_circuit_open():
                    # Mark unattempted rows explicitly; the next provider may still recover them.
                    rest=[x for x in remaining if x not in {y for pack0 in packs[:packs.index(pack)+1] for y in pack0}]
                    for text in rest:
                        prior=results.get(text); prior_status=prior.status if prior else "NOT_RUN"
                        results[text]=TranslationResult("","MYMEMORY_PUBLIC",f"PRIMARY:{prior_status};FALLBACK:FAILED:CIRCUIT_OPEN")
                    next_remaining.extend(rest)
                    break
        elif provider=="LINGVA":
            max_items=max(1,min(3,int(os.getenv("TRANSLATION_LINGVA_BATCH_SIZE","2"))))
            max_chars=max(160,int(os.getenv("TRANSLATION_LINGVA_MAX_CHARS","300")))
            for pack in _pack_texts(remaining,max_items,max_chars):
                fb=_translate_lingva_batch(pack)
                for text in pack:
                    res=fb.get(text,TranslationResult("","LINGVA_PUBLIC","FAILED:NOT_RETURNED"))
                    if res.text_zh:
                        results[text]=res
                        with _CACHE_LOCK: _CACHE[text]=res
                    else:
                        prior=results.get(text); prior_status=prior.status if prior else "NOT_RUN"
                        results[text]=TranslationResult("",res.provider,f"PRIMARY:{prior_status};FALLBACK:{res.status}")
                        next_remaining.append(text)
                if _lingva_circuit_open():
                    break
        remaining=list(dict.fromkeys(next_remaining))


def _translate_local_rule(text: str) -> TranslationResult:
    """Guaranteed offline Traditional-Chinese safety net for public-news headlines.

    This is deliberately labeled PARTIAL: it is a deterministic Chinese event
    rendering, not a machine-translation claim.  It exists so the UI never loses
    the Chinese reading layer when every public translation provider is throttled.
    English evidence remains authoritative and unchanged.
    """
    src=" ".join((text or "").split()).strip()
    if not src:
        return TranslationResult("", "LOCAL_RULE_ZH_TW", "EMPTY_INPUT")
    low=src.lower()
    # High-frequency policy/event templates observed in this system.
    patterns=[
        (r"supreme court.*(?:mail|vote-by-mail|mail-in|ballot)", "美國最高法院允許川普政府推進郵寄投票限制措施"),
        (r"(?:canada|canadian).*(?:car|cars|truck|trucks|auto|vehicle).*(?:tariff|tariffs).*(?:50%|50 percent)", "川普宣布／威脅將加拿大汽車與卡車關稅提高至50%"),
        (r"(?:canada|canadian).*(?:50%|50 percent).*(?:tariff|tariffs).*(?:car|cars|truck|trucks|auto|vehicle)", "川普宣布／威脅將加拿大汽車與卡車關稅提高至50%"),
        (r"(?:tariff|tariffs).*(?:canada|canadian).*(?:50%|50 percent).*(?:car|cars|truck|trucks|auto|vehicle)", "川普宣布／威脅將加拿大汽車與卡車關稅提高至50%"),
        (r"(?:anti-iran|iran).*(?:sanction|sanctions)", "川普政府宣布針對伊朗的制裁措施／全球制裁計畫"),
        (r"remarks from secretary of the treasury.*operation economic outcast", "美國財政部長就「經濟孤立行動」及對伊朗經濟制裁措施發表談話"),
        (r"operation economic outcast.*(?:iran|iranian)|(?:iran|iranian).*operation economic outcast", "「經濟孤立行動」：美國推動全面孤立伊朗政權的經濟制裁措施"),
        (r"secret service.*iran.*(?:threat|threatening).*barron", "美國特勤局注意到伊朗媒體發布威脅巴倫・川普安全的內容"),
        (r"approval.*(?:iran war|war).*poll|poll.*approval", "民調顯示川普支持度與美國民眾對伊朗戰爭支持出現變化"),
        (r"h-?1b.*(?:fee|fees)", "川普政府推動H-1B簽證費用政策調整"),
        (r"(?:immigration|deport|deported|border|asylum|visa|ice)", "川普政府移民／邊境政策相關事件"),
        (r"federal register|temporary suspension of additional duties", "美國聯邦公報公布與關稅／附加稅調整相關的正式文件"),
        (r"secretary of the treasury.*(?:iran|outcast)|treasury.*(?:iran|sanction)", "美國財政部公布與伊朗制裁／金融政策相關的官方訊息"),
        (r"canada.*retaliatory tariff|retaliatory tariff.*canada", "加拿大宣布報復性關稅，以回應川普政府的貿易施壓"),
        (r"canada.*(?:tariff|tariffs|trade war)|(?:tariff|tariffs|trade war).*canada", "美加關稅／貿易衝突出現新的政策行動或升級"),
        (r"(?:tariff|tariffs|trade war)", "川普政府關稅／國際貿易政策出現新進展"),
        (r"(?:iran|hormuz|military|war|sanction)", "川普政府地緣政治／能源與國安相關事件"),
        (r"(?:election|ballot|voting|vote|senate|congress|supreme court)", "川普政府美國政治／選舉制度相關事件"),
        (r"(?:medicaid|vaccine|healthcare|health care)", "川普政府醫療／社會政策相關事件"),
    ]
    for pat,zh in patterns:
        if re.search(pat, low):
            return TranslationResult(zh, "LOCAL_RULE_ZH_TW", "SUCCESS:LOCAL_RULE_PARTIAL")

    # Generic but transparent final safety net.  It provides a Chinese reading
    # label without pretending the untranslated proper content is a full MT result.
    cleaned=re.sub(r"\s+-\s+[^-]{2,80}$", "", src).strip()
    # Replace only stable high-frequency terms, preserve names/numbers.
    terms=[
        (r"\bTrump(?:'s)?\b", "川普"), (r"\bU\.S\.\b|\bUS\b", "美國"),
        (r"\bannounces?\b", "宣布"), (r"\bthreatens?\b", "威脅"),
        (r"\bsays?\b", "表示"), (r"\badministration\b", "政府"),
        (r"\btariffs?\b", "關稅"), (r"\bsanctions?\b", "制裁"),
        (r"\bSupreme Court\b", "最高法院"), (r"\bCanada\b|\bCanadian\b", "加拿大"),
        (r"\bIran\b|\bIranian\b", "伊朗"), (r"\bChina\b", "中國"),
        (r"\belection\b", "選舉"), (r"\btrade war\b", "貿易戰"),
    ]
    mixed=cleaned
    for pat,rep in terms:
        mixed=re.sub(pat,rep,mixed,flags=re.I)
    return TranslationResult("【規則式繁中摘要】"+mixed, "LOCAL_RULE_ZH_TW", "SUCCESS:LOCAL_RULE_PARTIAL")


def _apply_local_rule_fallback(texts: list[str], results: dict[str, TranslationResult]) -> None:
    """Fill only rows that still have no Chinese after all network providers."""
    for text in texts:
        current=results.get(text)
        if current is not None and current.text_zh:
            continue
        local=_translate_local_rule(text)
        if current is not None and current.status:
            local=TranslationResult(local.text_zh, local.provider, f"{local.status};NETWORK:{current.provider}:{current.status}")
        results[text]=local
        # LOCAL_RULE_ZH_TW is intentionally not persisted/cached.  Each new run
        # must retry the network/LLM providers so a transient outage can recover
        # to a full translation instead of being permanently pinned to PARTIAL.

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
            if not result.text_zh and _fallback_providers():
                tmp={clean: result}
                _fallback_pending([clean], tmp)
                result=tmp[clean]
    except Exception as exc:
        logger.warning("translation failed | provider=%s | error=%s | text=%s", provider, type(exc).__name__, clean[:120])
        result = TranslationResult("", provider, f"FAILED:{type(exc).__name__}")
    if not result.text_zh:
        network_provider, network_status = result.provider, result.status
        local = _translate_local_rule(clean)
        result = TranslationResult(local.text_zh, local.provider, f"{local.status};NETWORK:{network_provider}:{network_status}")
        logger.warning("translation network unavailable; local fallback used | network_provider=%s | network_status=%s | text=%s", network_provider, network_status, clean[:120])
    if result.text_zh and contains_cjk(result.text_zh):
        if result.provider != "LOCAL_RULE_ZH_TW":
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

        if google_failed and _fallback_providers():
            _fallback_pending(list(dict.fromkeys(google_failed)), results)
        # V2.3.17: if every public provider is throttled/unavailable, keep the
        # bilingual UI usable with a clearly-labeled offline partial Chinese layer.
        still_missing=[t for t in dict.fromkeys(google_failed) if not results.get(t) or not results[t].text_zh]
        if still_missing:
            logger.warning("translation public providers exhausted; local fallback | rows=%d", len(still_missing))
        _apply_local_rule_fallback(still_missing, results)
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
        _apply_local_rule_fallback(pending, results)
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

    # Guaranteed final offline safety net only when translation is enabled.
    if _enabled() and provider != "OFF":
        _apply_local_rule_fallback(unique, results)

    # Ensure every requested string has an explicit result even if a fallback circuit opened mid-run.
    for text in unique:
        results.setdefault(text, TranslationResult("", provider, "FAILED:NOT_ATTEMPTED"))
    success = sum(1 for r in results.values() if r.text_zh)
    failed = len(unique) - success
    attempted_counts: dict[str, int] = {}
    success_counts: dict[str, int] = {}
    status_counts: dict[str, int] = {}
    for r in results.values():
        attempted_counts[r.provider] = attempted_counts.get(r.provider, 0) + 1
        if r.text_zh:
            success_counts[r.provider] = success_counts.get(r.provider, 0) + 1
        status_key = r.status.split(":", 2)[0:2]
        status_label = ":".join(status_key)
        status_counts[status_label] = status_counts.get(status_label, 0) + 1
    attempted = ",".join(f"{k}:{v}" for k,v in sorted(attempted_counts.items())) or "NONE"
    effective = ",".join(f"{k}:{v}" for k,v in sorted(success_counts.items())) or "NONE"
    statuses = ",".join(f"{k}:{v}" for k,v in sorted(status_counts.items())) or "NONE"
    full_success = sum(1 for r in results.values() if r.text_zh and r.provider != "LOCAL_RULE_ZH_TW")
    local_partial = sum(1 for r in results.values() if r.text_zh and r.provider == "LOCAL_RULE_ZH_TW")
    logger.info("translation batch | requested=%d | success=%d | full_success=%d | local_partial=%d | failed=%d | primary_provider=%s | attempted_providers=%s | effective_success_providers=%s | result_statuses=%s | elapsed=%.2fs", len(unique), success, full_success, local_partial, failed, provider, attempted, effective, statuses, time.monotonic()-started)
    return results
