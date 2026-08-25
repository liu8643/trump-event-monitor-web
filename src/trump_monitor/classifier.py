from __future__ import annotations
import re
from trump_monitor.models import RawItem

KEYWORDS = {
    "移民／邊境政策": [r"\bimmigration\b",r"\bdeport(?:ed|ation|ations)?\b",r"\bborder\b",r"\basylum\b",r"\bice\b",r"\bvisa(s)?\b",r"\bh-?1b\b"],
    "法律／監管／倫理": [r"\bfinancial disclosure\b",r"\bholdings?\b",r"\bstocks? gained\b",r"\bconflict of interest\b",r"\bethics?\b",r"\binsider\b",r"\bsubpoena\b",r"\binvestigation\b"],
    "總統安全／國安": [r"\bsecret service\b",r"\bair force one\b",r"\bsecret flight\b",r"\bassassinat",r"\bsecurity threat\b",r"\bthreats? against trump\b"],
    "醫療／社會政策": [r"\bmedicaid\b",r"\bvaccine(s)?\b",r"\bmmr\b",r"gender[- ]affirming",r"transgender",r"\bhealth care\b",r"\bhealthcare\b"],
    "地緣政治／能源": [r"\biran(?:ian)?\b",r"\bhormuz\b",r"\bwar\b",r"\bstrike(s|d)?\b",r"\bmilitary\b",r"\boil\b",r"\bisrael\b"],
    "關稅／國際貿易": [r"\btariff(s)?\b",r"\btrade\b",r"\bcustoms\b",r"\bdut(y|ies)\b"],
    "美國政治／選舉制度": [r"\bsenate\b",r"\belection\b",r"\bvot(e|ing)\b",r"\bcongress\b",r"\bballot\b",r"\bsupreme court\b",r"\bnominee\b"],
    "社群訊號／TMTG": [r"\btmtg\b",r"\bdjt\b",r"truth social (traffic|revenue|contract|subscription|business)",r"posting spree"],
    "AI／半導體": [r"\bartificial intelligence\b",r"\bai\b",r"\bchip(s)?\b",r"\bsemiconductor(s)?\b",r"\bnvidia\b",r"\btsmc\b"],
}

def classify_category(item: RawItem) -> str:
    text=f"{item.title} {item.body}".lower()
    if re.search(r"\b(immigration|deport(?:ed|ation|ations)?|border|asylum|ice|visa(s)?|h-?1b)\b", text): return "移民／邊境政策"
    if re.search(r"\b(financial disclosure|holdings?|stocks? gained|conflict of interest|ethics?|insider|subpoena|investigation)\b", text): return "法律／監管／倫理"
    if re.search(r"\btmtg\b|\bdjt\b|truth social (traffic|revenue|contract|subscription|business)|posting spree", text): return "社群訊號／TMTG"
    scores={cat:sum(1 for pattern in patterns if re.search(pattern,text)) for cat,patterns in KEYWORDS.items()}
    best,count=max(scores.items(),key=lambda kv:kv[1])
    return best if count>0 else "其他／一般政治"

def classify_source_type(item: RawItem) -> str:
    # Search-index discovery is not the original Truth post and must not receive direct evidence weight.
    if item.acquisition_method == "SEARCH_INDEX": return "UNCONFIRMED"
    if item.acquisition_method in {"LICENSED_API","MANUAL_IMPORT"} and "truth" in item.publisher_group.lower(): return "DIRECT_POST"
    if item.source_name.lower() in {"white house","federal register","u.s. treasury"}: return "OFFICIAL_POLICY"
    if item.source_confidence < .45: return "UNCONFIRMED"
    if any(k in item.title.lower() for k in ["opinion","analysis","commentary"]): return "COMMENTARY"
    return "MEDIA_REPORT"
