from __future__ import annotations

from trump_monitor.models import EventScore, RawItem

HIGH_IMPACT_CATEGORIES = {
    "地緣政治／能源", "總統安全／國安", "關稅／國際貿易", "AI／半導體",
}
MEDIUM_IMPACT_CATEGORIES = {
    "美國政治／選舉制度", "社群訊號／TMTG", "醫療／社會政策",
}


def score_materiality(items: list[RawItem], category: str, score: EventScore) -> tuple[int, str, bool]:
    """0-100 event materiality gate, separate from market direction score."""
    publishers = {x.publisher_group.strip().lower() for x in items if x.publisher_group.strip()}
    verification = {
        x.publisher_group.strip().lower() for x in items
        if x.source_tier == 2 or x.publisher_group.strip().lower() in {"reuters", "ap", "ap news", "associated press", "bloomberg", "bloomberg.com"}
    }
    direct = any(x.source_tier == 1 or x.source_type in {"DIRECT_POST", "OFFICIAL_POLICY"} for x in items)
    unconfirmed_only = bool(items) and all(x.source_type in {"UNCONFIRMED", "COMMENTARY"} for x in items)

    total = 10 + score.importance * 7 + round(score.confidence * 10)
    if category in HIGH_IMPACT_CATEGORIES:
        total += 18
    elif category in MEDIUM_IMPACT_CATEGORIES:
        total += 8
    if direct:
        total += 12
    if verification:
        total += min(12, 6 + 3 * (len(verification) - 1))
    if len(publishers) >= 2:
        total += min(10, 4 + 2 * (len(publishers) - 2))
    if unconfirmed_only:
        total -= 20
    total = max(0, min(100, int(total)))

    if total >= 85:
        level = "BLACK"
    elif total >= 75:
        level = "RED"
    elif total >= 65:
        level = "ORANGE"
    elif total >= 55:
        level = "YELLOW"
    else:
        level = "WATCH"
    return total, level, total >= 65
