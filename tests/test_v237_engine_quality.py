from datetime import datetime, timezone
from pathlib import Path

from trump_monitor.classifier import classify_category
from trump_monitor.collectors.sample import SampleAdapter
from trump_monitor.config import AppConfig
from trump_monitor.engine import TrumpEventEngine
from trump_monitor.logging_utils import build_debug_bundle, configure_logging
from trump_monitor.models import RawItem, RunResult
from trump_monitor.source_health import build_source_health


def _item(title: str, body: str = "", publisher: str = "AP News") -> RawItem:
    return RawItem(raw_item_id=title[:20],source_name=publisher,publisher_group=publisher,source_type="MEDIA_REPORT",published_at=datetime(2026,8,12,tzinfo=timezone.utc),title=title,body=body,url="https://example.test",source_confidence=.9,source_tier=2,source_role="VERIFICATION")


def test_medicaid_chip_not_semiconductor():
    assert classify_category(_item("Trump administration ends Medicaid CHIP funding for gender-affirming care")) == "醫療／社會政策"


def test_secret_flight_security_category():
    assert classify_category(_item("Trump says Secret Service ordered secret flight change from Air Force One")) == "總統安全／國安"


def test_engine_uses_event_clustering_not_category_bucket():
    root=Path(__file__).resolve().parents[1]
    result=TrumpEventEngine(AppConfig(mode="SAMPLE"),[SampleAdapter(root/"data"/"sample_items.json")]).run(datetime(2026,7,28,0,0,tzinfo=timezone.utc))
    assert len(result.events) >= 4
    assert all(hasattr(e,"materiality_score") for e in result.events)


def test_ap_news_alias_counted():
    event_item=_item("Trump policy update")
    from trump_monitor.models import EventCluster, EventScore
    event=EventCluster(event_id="E",topic="x",category="其他／一般政治",summary="x",first_seen=event_item.published_at,last_seen=event_item.published_at,source_count=1,sources=[event_item],score=EventScore(rule_score=1,ai_score=0,final_score=1,confidence=.8,importance=1),impacts=[])
    result=RunResult(run_id="R",started_at=event_item.published_at,completed_at=event_item.published_at,lookback_hours=72,timezone="Asia/Taipei",status="SUCCESS",rule_version="x",prompt_version="x",model_version="x",schema_version="x",source_status={"google_news_rss":"SUCCESS:1"},events=[event])
    rows=build_source_health(result)
    ap=next(r for r in rows if r["來源"]=="AP")
    assert ap["筆數"] == 1 and ap["state"] == "SUCCESS"


def test_debug_bundle_download_artifact(tmp_path):
    logger=configure_logging(tmp_path)
    logger.info("runtime evidence")
    bundle=build_debug_bundle(tmp_path,"TEST")
    assert bundle.exists() and bundle.stat().st_size > 0


def test_truth_social_channel_name_does_not_hijack_event_topic():
    item=_item("Truth Social original post: Iran peace talks and military options", "Iran negotiations continue", "Truth Social")
    assert classify_category(item) == "地緣政治／能源"


def test_two_unrelated_items_same_category_stay_separate_events():
    from trump_monitor.models import RawItem
    class Adapter:
        name="memory"
        def collect(self,start,end):
            return [
                RawItem(raw_item_id="a",source_name="Reuters",publisher_group="Reuters",source_type="MEDIA_REPORT",published_at=datetime(2026,8,12,tzinfo=timezone.utc),title="Trump discusses Iran military options and oil risks",body="Tehran nuclear talks",url="https://a",source_confidence=.9,source_tier=2,source_role="VERIFICATION"),
                RawItem(raw_item_id="b",source_name="Reuters",publisher_group="Reuters",source_type="MEDIA_REPORT",published_at=datetime(2026,8,12,tzinfo=timezone.utc),title="Trump comments on Israel war cabinet and regional oil supply",body="Israel regional conflict",url="https://b",source_confidence=.9,source_tier=2,source_role="VERIFICATION"),
            ]
    result=TrumpEventEngine(AppConfig(mode="ONLINE"),[Adapter()]).run(datetime(2026,8,12,6,tzinfo=timezone.utc))
    assert len(result.events) == 2
