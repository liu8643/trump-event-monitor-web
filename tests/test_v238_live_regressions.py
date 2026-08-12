from datetime import datetime, timezone
from trump_monitor.models import RawItem, EventScore
from trump_monitor.clustering import cluster_items
from trump_monitor.materiality import score_materiality
from trump_monitor.taiwan_stocks import rank_candidates


def item(i,title,publisher,cat_tier=2,body=""):
    return RawItem(raw_item_id=i,source_name=publisher,publisher_group=publisher,source_type="MEDIA_REPORT",published_at=datetime(2026,8,12,tzinfo=timezone.utc),title=title,body=body,url=f"https://example.com/{i}",source_confidence=.9 if publisher in {"Reuters","AP News"} else .75,source_tier=cat_tier,source_role="VERIFICATION" if cat_tier==2 else "SUPPLEMENT")


def test_secret_flight_cross_category_is_one_event_family():
    rows=[
        item("r","Trump says his plane faced greater risk in secret flight change","Reuters"),
        item("a","Trump used elaborate ruse to fly out of Turkey following summit because of Iran threat","AP News"),
        item("n","Trump Said to Have Secretly Used Military Jet to Leave Turkey Amid Threats From Iran","New York Times",3),
        item("c","How a catering truck helped Trump secretly switch planes amid threat from Iran","PBS",3),
    ]
    cats={"r":"總統安全／國安","a":"地緣政治／能源","n":"地緣政治／能源","c":"地緣政治／能源"}
    groups=cluster_items(rows,cats)
    assert len(groups)==1
    assert groups[0][0]=="總統安全／國安"
    assert len(groups[0][1])==4


def test_reuters_iran_military_options_can_cross_material_gate():
    rows=[item("r","Trump says Iran options are let Tehran fail economically or hit them really hard","Reuters")]
    score=EventScore(rule_score=4,ai_score=0,final_score=1.4,confidence=.653,importance=3,breakdown={})
    total,level,is_material=score_materiality(rows,"地緣政治／能源",score)
    assert total >= 65
    assert is_material is True
    assert level in {"ORANGE","RED","BLACK"}


def test_no_material_events_means_no_candidates():
    assert rank_candidates([])==[]
