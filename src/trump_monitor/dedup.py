from __future__ import annotations

from hashlib import sha256
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
from difflib import SequenceMatcher

from trump_monitor.models import RawItem

TRACKING_KEYS = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "gclid", "fbclid"}


def canonicalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k.lower() not in TRACKING_KEYS]
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), urlencode(sorted(query)), ""))


def content_hash(item: RawItem) -> str:
    base = f"{item.title.strip().lower()}\n{item.body.strip().lower()}"
    return sha256(base.encode("utf-8")).hexdigest()


def _publisher_key(item: RawItem) -> str:
    return (item.publisher_group or item.source_name or "").strip().lower()


def _host(url: str) -> str:
    try:
        return urlsplit(url).netloc.lower().removeprefix("www.")
    except Exception:
        return ""


def _evidence_rank(item: RawItem) -> tuple:
    """Higher tuple means the duplicate row is the better retained evidence record.

    Prefer first-party / verification tier, direct publisher URLs over aggregator redirects,
    higher confidence, and richer text.  This prevents a Google RSS redirect from replacing
    a direct GDELT/official URL for the same publisher story.
    """
    acquisition = (item.acquisition_method or "").upper()
    direct_bonus = 1 if acquisition in {"WHITE_HOUSE_PUBLIC_PAGE", "GDELT_DOC_API_DIRECT_URL", "LICENSED_API", "MANUAL_IMPORT", "TRUTH_OFFICIAL_TIMELINE_PUBLIC_JSON"} else 0
    google_penalty = 1 if "GOOGLE_NEWS_RSS" in acquisition else 0
    return (-item.source_tier, direct_bonus, -google_penalty, item.source_confidence, len(item.body or ""), len(item.title or ""))


def deduplicate(items: list[RawItem], threshold: float = 0.88) -> tuple[list[RawItem], dict[str, str]]:
    """Deduplicate without destroying cross-publisher corroboration.

    Exact URL/content duplicates can collapse globally. Fuzzy-title deduplication is intentionally
    limited to the *same publisher/host*. Near-identical Reuters/AP/NBC headlines are independent
    evidence and must survive for event source-count / materiality calculations.
    """
    unique: list[RawItem] = []
    duplicate_of: dict[str, str] = {}
    seen_urls: dict[str, int] = {}
    seen_hashes: dict[str, int] = {}

    for item in sorted(items, key=lambda x: x.published_at):
        c_url = canonicalize_url(item.url)
        c_hash = content_hash(item)
        dup_idx: int | None = None

        if c_url and c_url in seen_urls:
            dup_idx = seen_urls[c_url]
        elif c_hash in seen_hashes:
            candidate_idx = seen_hashes[c_hash]
            candidate = unique[candidate_idx]
            if _publisher_key(candidate) == _publisher_key(item) or _host(candidate.url) == _host(item.url):
                dup_idx = candidate_idx
        if dup_idx is None:
            pkey = _publisher_key(item)
            host = _host(item.url)
            for idx, prev in enumerate(unique):
                same_publisher = bool(pkey) and pkey == _publisher_key(prev)
                same_host = bool(host) and host == _host(prev.url)
                if not (same_publisher or same_host):
                    continue
                ratio = SequenceMatcher(None, item.title.lower(), prev.title.lower()).ratio()
                if ratio >= threshold:
                    dup_idx = idx
                    break

        if dup_idx is None:
            idx = len(unique)
            unique.append(item)
            if c_url:
                seen_urls[c_url] = idx
            seen_hashes[c_hash] = idx
            continue

        prev = unique[dup_idx]
        # Keep the better evidence record while preserving duplicate mapping.
        if _evidence_rank(item) > _evidence_rank(prev):
            unique[dup_idx] = item
            duplicate_of[prev.raw_item_id] = item.raw_item_id
            if c_url:
                seen_urls[c_url] = dup_idx
            seen_hashes[c_hash] = dup_idx
        else:
            duplicate_of[item.raw_item_id] = prev.raw_item_id

    return unique, duplicate_of
