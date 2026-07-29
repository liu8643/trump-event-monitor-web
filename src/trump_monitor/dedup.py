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


def deduplicate(items: list[RawItem], threshold: float = 0.88) -> tuple[list[RawItem], dict[str, str]]:
    unique: list[RawItem] = []
    duplicate_of: dict[str, str] = {}
    seen_urls: dict[str, str] = {}
    seen_hashes: dict[str, str] = {}
    for item in sorted(items, key=lambda x: x.published_at):
        c_url = canonicalize_url(item.url)
        c_hash = content_hash(item)
        if c_url and c_url in seen_urls:
            duplicate_of[item.raw_item_id] = seen_urls[c_url]
            continue
        if c_hash in seen_hashes:
            duplicate_of[item.raw_item_id] = seen_hashes[c_hash]
            continue
        match_id = None
        for prev in unique:
            ratio = SequenceMatcher(None, item.title.lower(), prev.title.lower()).ratio()
            if ratio >= threshold:
                match_id = prev.raw_item_id
                break
        if match_id:
            duplicate_of[item.raw_item_id] = match_id
            continue
        unique.append(item)
        if c_url:
            seen_urls[c_url] = item.raw_item_id
        seen_hashes[c_hash] = item.raw_item_id
    return unique, duplicate_of
