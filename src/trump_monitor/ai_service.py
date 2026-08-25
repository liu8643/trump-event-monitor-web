from __future__ import annotations
import json, os, re
from dataclasses import dataclass
import requests

@dataclass
class AIAnalysis:
    category: str
    summary_zh: str
    sentiment: str
    confidence: float
    provider: str
    summary_status: str

KEYWORDS={
    "移民／邊境政策": [r"\bimmigration\b",r"\bdeport(?:ed|ation|ations)?\b",r"\bborder\b",r"\basylum\b",r"\bice\b",r"\bvisa(s)?\b",r"\bh-?1b\b"],
    "法律／監管／倫理": [r"\bfinancial disclosure\b",r"\bholdings?\b",r"\bstocks? gained\b",r"\bconflict of interest\b",r"\bethics?\b",r"\binsider\b",r"\bsubpoena\b",r"\binvestigation\b"],
    "總統安全／國安": [r"\bsecret service\b",r"\bair force one\b",r"\bsecret flight\b",r"\bassassinat",r"\bsecurity threat\b",r"\bthreats? against trump\b"],
    "醫療／社會政策": [r"\bmedicaid\b",r"\bvaccine(s)?\b",r"\bmmr\b",r"gender[- ]affirming",r"transgender",r"\bhealth care\b",r"\bhealthcare\b"],
 "關稅／國際貿易":[r"\btariff(s)?\b",r"\btrade\b",r"\bcustoms\b",r"\bdut(y|ies)\b"],
 "地緣政治／能源":[r"\biran(?:ian)?\b",r"\bisrael\b",r"\bwar\b",r"\boil\b",r"\bstrait\b",r"\bmilitary\b"],
 "AI／半導體":[r"\bartificial intelligence\b",r"\bai\b",r"\bchip(s)?\b",r"\bsemiconductor(s)?\b",r"\bnvidia\b"],
 "美國政治／選舉制度":[r"\bsenate\b",r"\belection\b",r"\bvot(e|ing)\b",r"\bcongress\b",r"\bballot\b",r"\bsupreme court\b",r"\bnominee\b"],
 "社群訊號／TMTG":[r"\btmtg\b",r"\bdjt\b",r"truth social (traffic|revenue|contract|subscription|business)"],
}

def heuristic_analyze(title:str,body:str)->AIAnalysis:
    text=(title+" "+body).lower()
    if re.search(r"\b(immigration|deport(?:ed|ation|ations)?|border|asylum|ice|visa(s)?|h-?1b)\b",text):
        category="移民／邊境政策"; best=99
    elif re.search(r"\b(financial disclosure|holdings?|stocks? gained|conflict of interest|ethics?|insider|subpoena|investigation)\b",text):
        category="法律／監管／倫理"; best=99
    elif re.search(r"\btmtg\b|\bdjt\b|truth social (traffic|revenue|contract|subscription|business)|posting spree",text):
        category="社群訊號／TMTG"; best=99
    else:
        category="其他／一般政治"; best=0
    if best<99:
        for cat,patterns in KEYWORDS.items():
            score=sum(1 for p in patterns if re.search(p,text))
            if score>best: category,best=cat,score
    neg=sum(bool(re.search(p,text)) for p in [r"\bwar\b",r"\battack",r"\bsanction",r"\btariff",r"\bthreat",r"\brisk"])
    pos=sum(bool(re.search(p,text)) for p in [r"\bdeal\b",r"\bpeace\b",r"\bagreement\b",r"\bgrowth\b",r"\bsupport\b",r"\bpause",r"\bceasefire\b"])
    sentiment="偏空" if neg>pos else "偏多" if pos>neg else "中性"
    summary=(body or title).strip().replace("\n"," ")[:420]
    return AIAnalysis(category,summary,sentiment,.66,"RULE_EXTRACTIVE_V2","EXTRACTIVE_SNIPPET")

def analyze(title:str,body:str)->AIAnalysis:
    url=os.getenv("AI_API_URL","").strip(); key=os.getenv("AI_API_KEY","").strip(); model=os.getenv("AI_MODEL","").strip()
    if not (url and key and model): return heuristic_analyze(title,body)
    prompt={"title":title,"body":body[:5000],"task":"Return JSON: category, summary_zh, sentiment, confidence"}
    try:
        r=requests.post(url,headers={"Authorization":f"Bearer {key}","Content-Type":"application/json"},json={"model":model,"messages":[{"role":"user","content":json.dumps(prompt,ensure_ascii=False)}],"temperature":0},timeout=30)
        r.raise_for_status(); data=json.loads(r.json()["choices"][0]["message"]["content"])
        return AIAnalysis(str(data["category"]),str(data["summary_zh"]),str(data["sentiment"]),float(data.get("confidence",.75)),f"LLM:{model}","LLM_ABSTRACTIVE")
    except Exception: return heuristic_analyze(title,body)
