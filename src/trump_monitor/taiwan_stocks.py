from __future__ import annotations
from pathlib import Path
import csv

DEFAULT_MAP={
"能源":[("6505","台塑化"),("9937","全國")],
"軍工":[("2634","漢翔"),("8033","雷虎"),("6753","龍德造船")],
"航空":[("2618","長榮航"),("2610","華航")],
"半導體":[("2330","台積電"),("2454","聯發科")],
"航運":[("2603","長榮"),("2609","陽明")],
"黃金":[("9955","佳龍")],
}

def load_map(path: str|Path|None=None):
    mapping=dict(DEFAULT_MAP)
    if path and Path(path).exists():
        with open(path,encoding="utf-8-sig",newline="") as f:
            for r in csv.DictReader(f): mapping.setdefault(r["sector"],[]).append((r["ticker"],r["name"]))
    return mapping

def rank_candidates(events, path=None):
    mapping=load_map(path); scores={}
    for e in events:
        for sector in e.beneficiary_sectors:
            for key, rows in mapping.items():
                if key in sector or sector in key:
                    for ticker,name in rows:
                        rec=scores.setdefault(ticker,{"ticker":ticker,"name":name,"score":0.0,"reasons":[]})
                        rec["score"] += max(0,e.score.final_score)*e.score.confidence
                        rec["reasons"].append(f"{e.event_id}:{sector}")
        for sector in e.negative_sectors:
            for key, rows in mapping.items():
                if key in sector or sector in key:
                    for ticker,name in rows:
                        rec=scores.setdefault(ticker,{"ticker":ticker,"name":name,"score":0.0,"reasons":[]})
                        rec["score"] -= max(1,abs(e.score.final_score))*e.score.confidence
                        rec["reasons"].append(f"{e.event_id}:{sector}(風險)")
    out=sorted(scores.values(),key=lambda x:x["score"],reverse=True)
    for i,r in enumerate(out,1): r["rank"]=i; r["action"]="WATCH"; r["reasons"]="；".join(r["reasons"])
    return out
