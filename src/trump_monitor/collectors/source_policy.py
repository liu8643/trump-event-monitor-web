from __future__ import annotations

VERIFICATION_PUBLISHERS = {"reuters", "associated press", "ap", "bloomberg"}


def publisher_tier(name: str) -> tuple[int, str]:
    value = name.strip().lower()
    if value in VERIFICATION_PUBLISHERS or any(x in value for x in ("reuters", "associated press", "bloomberg")):
        return 2, "VERIFICATION"
    return 3, "SUPPLEMENT"


SOURCE_PRIORITY_LABELS = [
    "1. Truth Social 第一手來源（授權API／人工匯入／搜尋索引發現）",
    "2. Reuters／AP／Bloomberg 交叉驗證",
    "3. Google News RSS 補充",
    "4. NewsAPI／GNews 補充",
]
