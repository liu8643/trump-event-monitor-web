from __future__ import annotations

from collections import defaultdict
from typing import Any

from trump_monitor.models import RunResult


SOURCE_HEALTH_ORDER = [
    ("truth_official_timeline", "Truth Official", "第一手公開時間軸"),
    ("truth_search_index", "Truth Search", "搜尋索引／降級發現"),
    ("publisher:reuters", "Reuters", "媒體交叉驗證"),
    ("publisher:ap", "AP", "媒體交叉驗證"),
    ("publisher:bloomberg", "Bloomberg", "媒體交叉驗證"),
    ("cnbc", "CNBC", "獨立 CNBC RSS 來源"),
    ("google_news_rss", "Google RSS", "聚合新聞補充"),
    ("newsapi", "NewsAPI", "API 補充"),
    ("gnews", "GNews", "API 補充"),
]


def _publisher_counts(result: RunResult) -> dict[str, int]:
    seen: dict[str, set[str]] = defaultdict(set)
    for event in result.events:
        for item in event.sources:
            name = (item.publisher_group or item.source_name or "").strip().lower()
            if not name:
                continue
            if "reuters" in name:
                seen["reuters"].add(item.raw_item_id)
            if name in {"ap", "associated press"} or "associated press" in name:
                seen["ap"].add(item.raw_item_id)
            if "bloomberg" in name:
                seen["bloomberg"].add(item.raw_item_id)
    return {key: len(ids) for key, ids in seen.items()}


def _state_from_status(status: str, count: int) -> tuple[str, str, int]:
    value = (status or "").upper()
    if count > 0 or value.startswith("SUCCESS"):
        return "SUCCESS", "🟢 成功", 100
    if value.startswith("FAILED"):
        return "FAILED", "🔴 失敗", 0
    if value.startswith("NO_DATA"):
        return "NO_DATA", "🟡 無資料", 0
    if value in {"NOT_CONFIGURED", "SKIPPED", "DISABLED", ""}:
        return "NOT_CONFIGURED", "⚪ 未設定", 0
    return "PARTIAL", "🟡 部分", 50


def build_source_health(result: RunResult) -> list[dict[str, Any]]:
    """Return stable, homepage-ready source health rows.

    Adapter-level sources use ``source_status`` / ``source_counts``.
    Reuters/AP/Bloomberg are publisher-level counts derived from the deduplicated
    evidence rows retained in the event result, because they arrive mainly via
    the aggregate Google News RSS adapter rather than dedicated APIs.
    """
    publisher_counts = _publisher_counts(result)
    google_state = result.source_status.get("google_news_rss", "NOT_CONFIGURED")
    rows: list[dict[str, Any]] = []

    for key, label, role in SOURCE_HEALTH_ORDER:
        if key.startswith("publisher:"):
            publisher_key = key.split(":", 1)[1]
            count = publisher_counts.get(publisher_key, 0)
            if count > 0:
                raw_status = f"SUCCESS:{count}"
            elif google_state.startswith("FAILED"):
                raw_status = f"FAILED:UPSTREAM:{google_state}"
            elif google_state == "NOT_CONFIGURED":
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
        "not_configured": sum(row["state"] == "NOT_CONFIGURED" for row in rows),
    }
