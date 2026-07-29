from datetime import datetime,timezone
from trump_monitor.ai_service import heuristic_analyze
from trump_monitor.taiwan_stocks import rank_candidates
from trump_monitor.models import EventCluster,EventScore

def test_ai_rule_classifies_tariff():
    x=heuristic_analyze('Trump announces tariff','trade duty increase')
    assert '關稅' in x.category and x.provider=='RULE_AI_V2'

def test_taiwan_candidate_mapping():
    e=EventCluster(event_id='E1',topic='x',category='地緣政治／能源',summary='x',first_seen=datetime.now(timezone.utc),last_seen=datetime.now(timezone.utc),source_count=1,sources=[],score=EventScore(rule_score=4,ai_score=0,final_score=4,confidence=.9,importance=4),impacts=[],beneficiary_sectors=['軍工'],negative_sectors=[])
    rows=rank_candidates([e])
    assert rows and rows[0]['action']=='WATCH'
