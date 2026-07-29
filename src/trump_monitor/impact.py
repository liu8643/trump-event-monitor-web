from __future__ import annotations

from trump_monitor.models import EventScore, MarketImpact

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


def build_impacts(category: str, score: EventScore) -> list[MarketImpact]:
    mapping = MAPPING.get(category, {
        "美股": (0, "中性", "直接市場傳導有限", "", ""),
        "台股": (0, "中性", "直接市場傳導有限", "", ""),
        "原油": (0, "中性", "直接市場傳導有限", "", ""),
        "黃金": (0, "中性", "直接市場傳導有限", "", ""),
        "美元": (0, "中性", "直接市場傳導有限", "", ""),
    })
    out: list[MarketImpact] = []
    for asset, (base, direction, rationale, beneficiary, negative) in mapping.items():
        sign = 1 if base >= 0 else -1
        adjusted = int(max(-5, min(5, round(base * max(0.5, min(1.2, abs(score.final_score) / 3.0 or 0.5))))))
        out.append(MarketImpact(
            asset=asset,
            rule_score=adjusted,
            ai_score=adjusted,
            final_score=adjusted,
            confidence=score.confidence,
            direction=direction,
            rationale=rationale,
            beneficiary=beneficiary,
            negative=negative,
        ))
    return out
