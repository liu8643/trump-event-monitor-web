from __future__ import annotations

import re
from trump_monitor.models import EventScore, RawItem

HIGH_IMPACT_CATEGORIES = {
    "地緣政治／能源", "總統安全／國安", "關稅／國際貿易", "AI／半導體",
}
MEDIUM_IMPACT_CATEGORIES = {
    "美國政治／選舉制度", "社群訊號／TMTG", "醫療／社會政策",
}


def _semantic_severity(items: list[RawItem], category: str) -> int:
    text=" ".join(f"{x.title} {x.body[:700]}" for x in items).lower()
    bonus=0
    if category == "地緣政治／能源" and re.search(r"\b(strike|attack|military option|military options|hit them really hard|war|blockade|hormuz)\b", text):
        bonus=max(bonus,10)
    if category == "總統安全／國安" and re.search(r"\b(assassinat|secret service|air force one|secret flight|secretly switch|decoy plane|catering truck|security threat|threat)\b", text):
        bonus=max(bonus,10)
    if category == "關稅／國際貿易" and re.search(r"\b(signed|effective|takes effect|impose|imposed|raise tariffs?|executive order|proclamation)\b", text):
        bonus=max(bonus,8)
    if category == "醫療／社會政策" and re.search(r"\b(ends?|ending|ban|bans|funding|rule|effective|administration)\b", text):
        bonus=max(bonus,5)
    return bonus


def score_materiality(items: list[RawItem], category: str, score: EventScore) -> tuple[int, str, bool]:
    """0-100 materiality gate independent of market direction.

    V2.3.8 adds semantic severity so a single Reuters/AP report about a genuinely
    consequential military/security action is not forced below the gate merely
    because duplicate coverage has not yet clustered. Multi-source evidence still
    increases confidence and remains the preferred path to RED/BLACK levels.
    """
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
    total += _semantic_severity(items, category)
    if direct:
        total += 12
    if verification:
        total += min(12, 6 + 3 * (len(verification) - 1))
    if len(publishers) >= 2:
        total += min(10, 4 + 2 * (len(publishers) - 2))
    if unconfirmed_only:
        total -= 20
    total = max(0, min(100, int(total)))

    if total >= 85: level = "BLACK"
    elif total >= 75: level = "RED"
    elif total >= 65: level = "ORANGE"
    elif total >= 55: level = "YELLOW"
    else: level = "WATCH"
    return total, level, total >= 65
