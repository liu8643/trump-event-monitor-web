from __future__ import annotations
import re
from trump_monitor.models import EventScore, MarketImpact, RawItem

MAPPING={
 "地緣政治／能源":{"美股":(-2,"中性偏空","地緣風險提高風險溢價","軍工、能源","航空、運輸"),"台股":(-1,"中性偏空","外資風險偏好可能下降","軍工、能源","高Beta電子"),"原油":(3,"偏多","供應中斷風險","上游能源、油輪","航空、運輸"),"黃金":(2,"偏多","避險需求上升","黃金、貴金屬","高Beta資產"),"美元":(1,"中性偏多","避險美元需求","美元資產","新興市場貨幣")},
 "關稅／國際貿易":{"美股":(-1,"中性偏空","成本與供應鏈不確定性","美國在地製造","跨境科技、汽車"),"台股":(-2,"偏空","出口導向供應鏈受壓","在美設廠供應鏈","電子代工、汽車零組件"),"原油":(0,"中性","需求與通膨效果互抵","",""),"黃金":(1,"中性偏多","政策不確定性","黃金",""),"美元":(1,"中性偏多","貿易風險與資金避險","美元","非美貨幣")},
}

def _event_factor(items:list[RawItem])->int:
    text=' '.join(f'{x.title} {x.body}' for x in items).lower()
    # De-escalation reverses the standard geopolitical risk transmission.
    if re.search(r'pause(s|d)? attacks|ceasefire|peace deal|halts? bombing|de-escalat',text): return -1
    return 1

def build_impacts(category:str,score:EventScore,items:list[RawItem]|None=None)->list[MarketImpact]:
    mapping=MAPPING.get(category,{a:(0,"中性","直接市場傳導有限","","") for a in ["美股","台股","原油","黃金","美元"]})
    factor=_event_factor(items or []) if category=="地緣政治／能源" else 1
    out=[]
    strength=max(.5,min(1.2,abs(score.final_score)/3.0 or .5))
    for asset,(base,direction,rationale,beneficiary,negative) in mapping.items():
        effective=base*factor
        adjusted=int(max(-5,min(5,round(effective*strength))))
        if factor==-1 and adjusted:
            direction="偏多" if adjusted>0 else "偏空"
            rationale="地緣風險降溫，原有風險溢價方向反轉"
            beneficiary,negative=negative,beneficiary
        out.append(MarketImpact(asset=asset,rule_score=adjusted,ai_score=adjusted,final_score=adjusted,confidence=score.confidence,direction=direction,rationale=rationale,beneficiary=beneficiary,negative=negative))
    return out
