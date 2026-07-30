from __future__ import annotations

VERIFICATION_PUBLISHERS = {"reuters", "associated press", "ap", "bloomberg"}


def publisher_tier(name: str) -> tuple[int, str]:
    value = name.strip().lower()
    if value in VERIFICATION_PUBLISHERS or any(x in value for x in ("reuters", "associated press", "bloomberg")):
        return 2, "VERIFICATION"
    return 3, "SUPPLEMENT"


SOURCE_PRIORITY_LABELS = [
    "1. Truth Social Official Timeline（@realDonaldTrump 公開時間軸；最高優先）",
    "1A. Truth Social 授權API／人工匯入（原有來源保留）",
    "1B. Truth Social 搜尋索引（僅發現用途；原有來源保留）",
    "2. Reuters／AP／Bloomberg 交叉驗證",
    "3. Google News RSS 補充",
    "4. NewsAPI／GNews 補充",
]
