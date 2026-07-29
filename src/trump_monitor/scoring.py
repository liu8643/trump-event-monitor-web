from __future__ import annotations
from statistics import mean
from trump_monitor.models import RawItem, EventScore


def score_event(items: list[RawItem], category: str, ai_score: float = 0.0) -> EventScore:
    breakdown={}
    if any(x.source_type=="DIRECT_POST" for x in items): breakdown["truth_primary"] = 3
    if any(x.source_type=="OFFICIAL_POLICY" for x in items): breakdown["official_policy"] = 3
    if category in {"地緣政治／能源","關稅／國際貿易","AI／半導體"}: breakdown["market_sensitive"] = 2
    verification={x.publisher_group for x in items if x.source_tier==2 or x.publisher_group.lower() in {"reuters","associated press","ap","bloomberg"}}
    if verification: breakdown["verification_source"] = 2
    publishers={x.publisher_group for x in items}
    if len(publishers)>=2: breakdown["multi_source"] = 1
    if all(x.source_type in {"COMMENTARY","UNCONFIRMED"} for x in items): breakdown["low_evidence"]=-2
    rule_score=sum(breakdown.values()); rule_norm=max(-5,min(5,rule_score/2)); final=max(-5,min(5,round(rule_norm*.7+ai_score*.3,2)))
    quality=mean(x.source_confidence for x in items); cross=min(1,len(publishers)/3); direct=1 if any(x.source_tier==1 or x.source_type in {"DIRECT_POST","OFFICIAL_POLICY"} for x in items) else .5
    consistency=.85 if len(items)>1 else .65; confidence=min(1,round(quality*.35+cross*.25+direct*.2+.9*.1+consistency*.1,3))
    importance=5 if rule_score>=8 else 4 if rule_score>=6 else 3 if rule_score>=4 else 2 if rule_score>=2 else 1
    return EventScore(rule_score=rule_score,ai_score=ai_score,final_score=final,confidence=confidence,importance=importance,breakdown=breakdown)
