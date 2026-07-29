from __future__ import annotations
from pathlib import Path
import json, csv

def update_watchlist(candidates, output_dir: str|Path):
    out=Path(output_dir); out.mkdir(parents=True,exist_ok=True)
    rows=[r for r in candidates if r.get("score",0)>0][:20]
    j=out/"gtc_watchlist_v2.json"; c=out/"gtc_watchlist_v2.csv"
    j.write_text(json.dumps({"schema":"gtc.watchlist.v2","mode":"REVIEW_REQUIRED","items":rows},ensure_ascii=False,indent=2),encoding="utf-8")
    with c.open("w",encoding="utf-8-sig",newline="") as f:
        w=csv.DictWriter(f,fieldnames=["rank","ticker","name","score","action","reasons"]); w.writeheader(); w.writerows(rows)
    return j,c
