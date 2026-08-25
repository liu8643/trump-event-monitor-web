from __future__ import annotations
from datetime import datetime, timezone

from trump_monitor.clustering import _event_family, cluster_items
from trump_monitor.classifier import classify_category
from trump_monitor.impact import build_impacts
from trump_monitor.models import RawItem
from trump_monitor.scoring import score_event
import trump_monitor.translation as tr


def _item(rid: str, title: str, publisher: str = "Reuters", tier: int = 2, source_type: str = "MEDIA_REPORT") -> RawItem:
    return RawItem(
        raw_item_id=rid, source_name=publisher, publisher_group=publisher, source_type=source_type,
        published_at=datetime(2026,8,25,3,tzinfo=timezone.utc), title=title, body="",
        url=f"https://example.com/{rid}", source_tier=tier,
        source_confidence=.99 if tier==1 else .90 if tier==2 else .68,
        source_role="PRIMARY" if tier==1 else "VERIFICATION" if tier==2 else "SUPPLEMENT",
        acquisition_method="OFFICIAL_DIRECT" if tier==1 else "GOOGLE_NEWS_RSS",
    )


def test_canada_percent_family_regex_matches_literal_percent():
    row=_item("r","Trump threatens 50% tariffs on all cars and trucks from Canada amid trade fight")
    assert _event_family(row)=="CANADA_50_AUTO_TARIFF_ACTION"


def test_scotus_mail_voting_live_titles_merge_one_family():
    rows=[
        _item("a","Supreme Court sides with Trump administration on mail voting restrictions ahead of midterms","AP News"),
        _item("c","Supreme Court allows some Trump vote-by-mail limits ahead of midterm election","CNBC"),
    ]
    cats={x.raw_item_id:"美國政治／選舉制度" for x in rows}
    groups=cluster_items(rows,cats)
    assert len(groups)==1 and len(groups[0][1])==2


def test_operation_economic_outcast_official_rows_merge():
    rows=[
        _item("t","Remarks from Secretary of the Treasury Scott Bessent on Operation Economic Outcast against Iran","U.S. Treasury",1,"OFFICIAL_POLICY"),
        _item("o","Operation Economic Outcast: Total Isolation of the Iranian Regime","U.S. Treasury",1,"OFFICIAL_POLICY"),
    ]
    cats={x.raw_item_id:classify_category(x) for x in rows}
    groups=cluster_items(rows,cats)
    assert len(groups)==1 and len(groups[0][1])==2
    assert classify_category(rows[1])=="地緣政治／能源"


def test_tariff_suspension_uses_easing_market_regime():
    rows=[_item("f","Temporary Suspension of Additional Duties To Offset Canadian Discrimination Against the Commerce of the United States With Respect to Alcoholic Beverages, Dairy, and Motor Vehicles","Federal Register",1,"OFFICIAL_POLICY")]
    cat="關稅／國際貿易"
    score=score_event(rows,cat)
    impacts={x.asset:x for x in build_impacts(cat,score,rows)}
    assert impacts["美股"].final_score >= 0
    assert impacts["台股"].final_score >= 0
    assert impacts["黃金"].final_score <= 0
    assert "暫停" in impacts["美股"].rationale or "下調" in impacts["美股"].rationale


def test_tariff_hike_keeps_escalation_market_regime():
    rows=[_item("r","Trump says U.S. will hike Canada auto tariffs to 50% as trade war escalates")]
    cat="關稅／國際貿易"
    score=score_event(rows,cat)
    impacts={x.asset:x for x in build_impacts(cat,score,rows)}
    assert impacts["美股"].final_score <= 0
    assert impacts["台股"].final_score < 0


def test_local_rule_retaliatory_tariff_preserves_action_semantics():
    r=tr._translate_local_rule("Canada to announce retaliatory tariffs as Trump tells its leaders to fall in line")
    assert "加拿大" in r.text_zh and "報復性關稅" in r.text_zh
    assert r.provider=="LOCAL_RULE_ZH_TW"


def test_local_rule_economic_outcast_uses_isolation_not_abandonment():
    r=tr._translate_local_rule("Operation Economic Outcast: Total Isolation of the Iranian Regime")
    assert "經濟孤立行動" in r.text_zh and "伊朗" in r.text_zh
