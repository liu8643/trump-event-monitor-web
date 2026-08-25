from __future__ import annotations

VERIFICATION_PUBLISHERS = {
    "reuters", "reuters.com",
    "associated press", "ap", "ap news", "apnews.com",
    "bloomberg", "bloomberg.com",
    "cnbc", "cnbc.com",
}


def normalize_publisher(name: str) -> str:
    value = (name or "").strip().lower()
    if value.startswith("www."):
        value = value[4:]
    return value


def is_verification_publisher(name: str) -> bool:
    value = normalize_publisher(name)
    if value in VERIFICATION_PUBLISHERS:
        return True
    return any(x in value for x in ("reuters", "associated press", "apnews", "bloomberg", "cnbc"))


def publisher_tier(name: str) -> tuple[int, str]:
    if is_verification_publisher(name):
        return 2, "VERIFICATION"
    return 3, "SUPPLEMENT"


SOURCE_PRIORITY_LABELS = [
    "1. Truth Social Official Timeline（@realDonaldTrump 公開時間軸；最高優先）",
    "1A. White House Official（白宮官方公告／聲明／總統行動；直接網址）",
    "1B. Truth Social 授權API／人工匯入（原有來源保留）",
    "1C. Truth Social 搜尋索引（僅發現用途；原有來源保留）",
    "2. Reuters／AP／Bloomberg／CNBC 媒體交叉驗證（來源層級依publisher；取得通道另行揭露）",
    "3. Google News RSS 聚合補充",
    "3A. GDELT DOC API 免Key直連新聞發現（直接publisher URL）",
    "4. NewsAPI／GNews 有Key時補充",
]
