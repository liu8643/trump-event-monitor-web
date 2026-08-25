from datetime import datetime, timezone

from trump_monitor.models import EventCluster, EventScore, RawItem, RunResult
from trump_monitor.source_health import build_source_health, source_health_summary


def _item(raw_id: str, publisher: str) -> RawItem:
    return RawItem(
        raw_item_id=raw_id,
        source_name=publisher,
        publisher_group=publisher,
        source_type="MEDIA_REPORT",
        published_at=datetime(2026, 7, 30, tzinfo=timezone.utc),
        title=f"{publisher} title",
        url=f"https://example.com/{raw_id}",
    )


def _result() -> RunResult:
    event = EventCluster(
        event_id="TRUMP-1",
        topic="topic",
        category="其他／一般政治",
        summary="summary",
        first_seen=datetime(2026, 7, 30, tzinfo=timezone.utc),
        last_seen=datetime(2026, 7, 30, tzinfo=timezone.utc),
        source_count=3,
        sources=[_item("r1", "Reuters"), _item("b1", "Bloomberg"), _item("a1", "Associated Press")],
        score=EventScore(rule_score=1, ai_score=1, final_score=1, confidence=.8, importance=2),
        impacts=[],
    )
    return RunResult(
        run_id="R1",
        started_at=datetime(2026, 7, 30, tzinfo=timezone.utc),
        completed_at=datetime(2026, 7, 30, tzinfo=timezone.utc),
        lookback_hours=72,
        timezone="Asia/Taipei",
        status="PARTIAL",
        rule_version="r",
        prompt_version="p",
        model_version="m",
        schema_version="gtc.trump_event.v2.2",
        source_status={
            "truth_official_timeline": "FAILED:SourceError:HTTP_403",
            "federal_register": "SUCCESS:2",
            "treasury_official": "SUCCESS:1",
            "truth_search_index": "SUCCESS:22",
            "cnbc": "SUCCESS:3",
            "google_news_rss": "SUCCESS:99",
        },
        source_counts={
            "truth_official_timeline": 0,
            "federal_register": 2,
            "treasury_official": 1,
            "truth_search_index": 22,
            "cnbc": 3,
            "google_news_rss": 99,
        },
        events=[event],
    )


def test_source_health_contains_all_homepage_sources_and_counts():
    rows = build_source_health(_result())
    by_name = {row["來源"]: row for row in rows}
    assert list(by_name) == ["Truth Official", "White House Official", "Federal Register", "U.S. Treasury", "Truth Search", "Reuters", "AP", "Bloomberg", "CNBC", "Google RSS", "GDELT", "NewsAPI", "GNews"]
    assert by_name["CNBC"]["筆數"] == 3
    assert by_name["Reuters"]["筆數"] == 1
    assert by_name["AP"]["筆數"] == 1
    assert by_name["Bloomberg"]["筆數"] == 1


def test_source_health_distinguishes_failed_no_data_and_not_configured():
    rows = build_source_health(_result())
    by_name = {row["來源"]: row for row in rows}
    assert by_name["Truth Official"]["state"] == "FAILED"
    assert by_name["Truth Official"]["覆蓋率"] == 0
    assert by_name["Truth Search"]["state"] == "SUCCESS"
    assert by_name["Truth Search"]["覆蓋率"] == 100
    assert by_name["NewsAPI"]["state"] == "NOT_CONFIGURED"
    summary = source_health_summary(rows)
    assert summary["success"] == 8
    assert summary["failed"] == 1
    assert summary["not_configured"] == 4


def test_source_health_summary_counts_partial():
    from trump_monitor.source_health import source_health_summary
    rows=[{"state":"SUCCESS"},{"state":"PARTIAL"},{"state":"FAILED"},{"state":"NO_DATA"},{"state":"NOT_CONFIGURED"}]
    summary=source_health_summary(rows)
    assert summary["partial"]==1
    assert summary["success"]==1
