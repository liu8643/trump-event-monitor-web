from __future__ import annotations

from collections import defaultdict
from typing import Any

from trump_monitor.models import RunResult


SOURCE_HEALTH_ORDER = [
    ("truth_official_timeline", "Truth Official", "第一手公開時間軸"),
    ("whitehouse_official", "White House Official", "第一手官方公告／聲明／總統行動直連"),
    ("truth_search_index", "Truth Search", "搜尋索引／降級發現"),
    ("publisher:reuters", "Reuters", "媒體publisher覆蓋（取得通道另列）"),
    ("publisher:ap", "AP", "媒體publisher覆蓋（取得通道另列）"),
    ("publisher:bloomberg", "Bloomberg", "媒體publisher覆蓋（取得通道另列）"),
    ("cnbc", "CNBC", "CNBC via Google News RSS source filter"),
    ("google_news_rss", "Google RSS", "聚合新聞補充"),
    ("gdelt", "GDELT", "免Key多來源新聞發現／直接publisher URL"),
    ("newsapi", "NewsAPI", "API 補充（需Key）"),
    ("gnews", "GNews", "API 補充（需Key）"),
]


def _publisher_evidence(result: RunResult) -> dict[str, dict[str, Any]]:
    ids: dict[str, set[str]] = defaultdict(set)
    channels: dict[str, set[str]] = defaultdict(set)
    for event in result.events:
        for item in event.sources:
            name = (item.publisher_group or item.source_name or "").strip().lower()
            if not name:
                continue
            keys: list[str] = []
            if "reuters" in name:
                keys.append("reuters")
            if name in {"ap", "ap news", "associated press", "apnews.com"} or "associated press" in name or "apnews" in name:
                keys.append("ap")
            if "bloomberg" in name:
                keys.append("bloomberg")
            for key in keys:
                ids[key].add(item.raw_item_id)
                channels[key].add(item.acquisition_method or "UNKNOWN")
    return {key: {"count": len(ids[key]), "channels": sorted(channels[key])} for key in set(ids) | set(channels)}


def _state_from_status(status: str, count: int) -> tuple[str, str, int]:
    value = (status or "").upper()
    if count > 0 or value.startswith("SUCCESS") or value.startswith("PUBLISHER_COVERAGE"):
        return "SUCCESS", "🟢 成功", 100
    if value.startswith("FAILED"):
        return "FAILED", "🔴 失敗", 0
    if value.startswith("NO_DATA"):
        return "NO_DATA", "🟡 無資料", 0
    if value in {"NOT_CONFIGURED", "SKIPPED", "DISABLED", ""}:
        return "NOT_CONFIGURED", "⚪ 未設定", 0
    return "PARTIAL", "🟡 部分", 50


def build_source_health(result: RunResult) -> list[dict[str, Any]]:
    """Stable source-health rows that separate publisher identity from acquisition channel."""
    publisher = _publisher_evidence(result)
    google_state = result.source_status.get("google_news_rss", "NOT_CONFIGURED")
    gdelt_state = result.source_status.get("gdelt", "NOT_CONFIGURED")
    rows: list[dict[str, Any]] = []

    for key, label, role in SOURCE_HEALTH_ORDER:
        if key.startswith("publisher:"):
            publisher_key = key.split(":", 1)[1]
            rec = publisher.get(publisher_key, {"count": 0, "channels": []})
            count = int(rec["count"])
            channels = rec["channels"]
            if count > 0:
                raw_status = f"PUBLISHER_COVERAGE:{count};VIA={','.join(channels) if channels else 'UNKNOWN'}"
            elif google_state.startswith("FAILED") and gdelt_state.startswith("FAILED"):
                raw_status = f"FAILED:UPSTREAM:GOOGLE={google_state};GDELT={gdelt_state}"
            elif google_state == "NOT_CONFIGURED" and gdelt_state == "NOT_CONFIGURED":
                raw_status = "NOT_CONFIGURED"
            else:
                raw_status = "NO_DATA:0"
        else:
            count = int(result.source_counts.get(key, 0))
            raw_status = result.source_status.get(key, "NOT_CONFIGURED")

        state, display_status, coverage = _state_from_status(raw_status, count)
        rows.append({
            "source_key": key,
            "來源": label,
            "筆數": count,
            "狀態": display_status,
            "state": state,
            "覆蓋率": coverage,
            "角色": role,
            "詳細狀態": raw_status,
        })
    return rows


def source_health_summary(rows: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "total": len(rows),
        "success": sum(row["state"] == "SUCCESS" for row in rows),
        "no_data": sum(row["state"] == "NO_DATA" for row in rows),
        "failed": sum(row["state"] == "FAILED" for row in rows),
        "partial": sum(row["state"] == "PARTIAL" for row in rows),
        "not_configured": sum(row["state"] == "NOT_CONFIGURED" for row in rows),
    }
