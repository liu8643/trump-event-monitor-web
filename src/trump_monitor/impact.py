from __future__ import annotations

import re
from trump_monitor.models import EventScore, MarketImpact, RawItem

MAPPING = {
    "地緣政治／能源": {
        "美股": (-2, "中性偏空", "地緣風險提高風險溢價", "軍工、能源", "航空、運輸"),
        "台股": (-1, "中性偏空", "外資風險偏好可能下降", "軍工、能源", "高Beta電子"),
        "原油": (3, "偏多", "供應中斷風險", "上游能源、油輪", "航空、運輸"),
        "黃金": (2, "偏多", "避險需求上升", "黃金、貴金屬", "高Beta資產"),
        "美元": (1, "中性偏多", "避險美元需求", "美元資產", "新興市場貨幣"),
    },
    "關稅／國際貿易": {
        "美股": (-1, "中性偏空", "成本與供應鏈不確定性", "美國在地製造", "跨境科技、汽車"),
        "台股": (-2, "偏空", "出口導向供應鏈受壓", "在美設廠供應鏈", "電子代工、汽車零組件"),
        "原油": (0, "中性", "需求與通膨效果互抵", "", ""),
        "黃金": (1, "中性偏多", "政策不確定性", "黃金", ""),
        "美元": (1, "中性偏多", "貿易風險與資金避險", "美元", "非美貨幣"),
    },
}

TRADE_EASING_MAPPING = {
    "美股": (1, "中性偏多", "關稅／附加稅暫停或下調，降低成本與政策不確定性", "汽車、零售、跨境供應鏈", "避險交易"),
    "台股": (1, "中性偏多", "關稅壓力緩和有利出口與跨境供應鏈風險偏好", "電子代工、汽車零組件", "純內需避險題材"),
    "原油": (0, "中性", "貿易摩擦緩和與需求預期效果有限", "", ""),
    "黃金": (-1, "中性偏空", "政策不確定性下降，部分避險需求降溫", "風險資產", "黃金"),
    "美元": (0, "中性", "風險偏好改善與政策差異互抵", "", ""),
}

def _trade_regime(items: list[RawItem] | None) -> str:
    if not items:
        return "ESCALATION_OR_GENERIC"
    text = " ".join(f"{x.title} {x.body[:700]}" for x in items).lower()
    easing = re.search(r"\b(suspend(?:ed|ing)?|suspension|pause(?:d)?|exempt(?:ion|ed|s)?|reduce(?:d|s)?|lower(?:ed|s)?|remove(?:d|s)?|lift(?:ed|s)?|waiv(?:e|ed|er)|rollback|roll back)\b", text)
    tariff = re.search(r"\b(tariff|tariffs|duties|duty|customs)\b", text)
    escalation = re.search(r"\b(hike|raise|increase|double|impose|retaliatory|threaten|escalat|50\s*(?:%|percent\b))\b", text)
    if tariff and easing and not escalation:
        return "EASING"
    return "ESCALATION_OR_GENERIC"

def build_impacts(category: str, score: EventScore, items: list[RawItem] | None = None) -> list[MarketImpact]:
    if category == "關稅／國際貿易" and _trade_regime(items) == "EASING":
        mapping = TRADE_EASING_MAPPING
    else:
        mapping = MAPPING.get(category, {
            "美股": (0, "中性", "直接市場傳導有限", "", ""),
            "台股": (0, "中性", "直接市場傳導有限", "", ""),
            "原油": (0, "中性", "直接市場傳導有限", "", ""),
            "黃金": (0, "中性", "直接市場傳導有限", "", ""),
            "美元": (0, "中性", "直接市場傳導有限", "", ""),
        })
    out: list[MarketImpact] = []
    for asset, (base, direction, rationale, beneficiary, negative) in mapping.items():
        adjusted = int(max(-5, min(5, round(base * max(0.5, min(1.2, abs(score.final_score) / 3.0 or 0.5))))))
        out.append(MarketImpact(asset=asset, rule_score=adjusted, ai_score=adjusted, final_score=adjusted,
            confidence=score.confidence, direction=direction, rationale=rationale, beneficiary=beneficiary, negative=negative))
    return out
