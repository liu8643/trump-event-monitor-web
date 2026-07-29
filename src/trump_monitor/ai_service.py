from __future__ import annotations
import json, os
from dataclasses import dataclass
import requests

@dataclass
class AIAnalysis:
    category: str
    summary_zh: str
    sentiment: str
    confidence: float
    provider: str

KEYWORDS = {
    "關稅／國際貿易": ["tariff", "trade", "customs", "duty"],
    "地緣政治／能源": ["iran", "israel", "war", "oil", "strait", "military"],
    "AI／半導體": ["ai", "chip", "semiconductor", "nvidia"],
    "美國政治／選舉制度": ["senate", "election", "vote", "congress"],
    "社群訊號／TMTG": ["truth social", "tmtg", "djt"],
}

def heuristic_analyze(title: str, body: str) -> AIAnalysis:
    text=(title+" "+body).lower()
    category="其他／一般政治"
    for cat, words in KEYWORDS.items():
        if any(w in text for w in words): category=cat; break
    neg=sum(w in text for w in ["war","attack","sanction","tariff","threat","risk"])
    pos=sum(w in text for w in ["deal","peace","agreement","growth","support"])
    sentiment="偏空" if neg>pos else "偏多" if pos>neg else "中性"
    summary=(body or title).strip().replace("\n"," ")[:420]
    return AIAnalysis(category, summary, sentiment, .66, "RULE_AI_V2")

def analyze(title: str, body: str) -> AIAnalysis:
    """Optional OpenAI-compatible endpoint; deterministic rule engine remains the safe fallback."""
    url=os.getenv("AI_API_URL","").strip(); key=os.getenv("AI_API_KEY","").strip(); model=os.getenv("AI_MODEL","").strip()
    if not (url and key and model): return heuristic_analyze(title,body)
    prompt={"title":title,"body":body[:5000],"task":"Return JSON: category, summary_zh, sentiment, confidence"}
    try:
        r=requests.post(url,headers={"Authorization":f"Bearer {key}","Content-Type":"application/json"},json={"model":model,"messages":[{"role":"user","content":json.dumps(prompt,ensure_ascii=False)}],"temperature":0},timeout=30)
        r.raise_for_status(); payload=r.json()
        content=payload["choices"][0]["message"]["content"]
        data=json.loads(content)
        return AIAnalysis(str(data["category"]),str(data["summary_zh"]),str(data["sentiment"]),float(data.get("confidence",.75)),f"LLM:{model}")
    except Exception:
        return heuristic_analyze(title,body)
