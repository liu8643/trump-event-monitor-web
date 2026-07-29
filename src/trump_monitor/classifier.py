from __future__ import annotations

from trump_monitor.models import RawItem

KEYWORDS = {
    "地緣政治／能源": ["iran", "hormuz", "war", "strike", "military", "oil"],
    "關稅／國際貿易": ["tariff", "trade", "eu", "canada", "auto"],
    "美國政治／選舉制度": ["senate", "voting", "save america", "filibuster", "ballot"],
    "社群訊號／TMTG": ["truth social", "ai image", "posting spree", "tmtg", "djt"],
    "AI／半導體": ["semiconductor", "nvidia", "tsmc", "chip", "ai"],
}


def classify_category(item: RawItem) -> str:
    text = f"{item.title} {item.body}".lower()
    scores = {category: sum(1 for k in keys if k in text) for category, keys in KEYWORDS.items()}
    best, count = max(scores.items(), key=lambda kv: kv[1])
    return best if count > 0 else "其他／一般政治"


def classify_source_type(item: RawItem) -> str:
    if "truthsocial.com" in item.url.lower() or item.source_name.lower() == "truth social":
        return "DIRECT_POST"
    if item.source_name.lower() in {"white house", "federal register", "u.s. treasury"}:
        return "OFFICIAL_POLICY"
    if item.source_confidence < 0.45:
        return "UNCONFIRMED"
    if any(k in item.title.lower() for k in ["opinion", "analysis", "commentary"]):
        return "COMMENTARY"
    return "MEDIA_REPORT"
