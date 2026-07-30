from datetime import datetime, timezone

from trump_monitor.collectors.base import SourceAdapter, SourceError
from trump_monitor.config import AppConfig
from trump_monitor.engine import TrumpEventEngine


class FailingTruth(SourceAdapter):
    name = "truth_official_timeline"
    def collect(self, start, end):
        raise SourceError("ACCESS_DENIED/HTTP_403")


def test_v223_schema_default_is_current():
    assert AppConfig().schema_version == "gtc.trump_event.v2.2"


def test_v223_truth_failure_preserves_reason():
    result = TrumpEventEngine(AppConfig(), [FailingTruth()]).run(datetime(2026, 7, 30, tzinfo=timezone.utc))
    assert "ACCESS_DENIED/HTTP_403" in result.source_status["truth_official_timeline"]
    assert "OFFICIAL_TIMELINE_FAILED" in result.truth_social_status


def test_truth_access_denied_is_not_reported_as_no_posts():
    from datetime import datetime, timezone
    from trump_monitor.config import AppConfig
    from trump_monitor.engine import TrumpEventEngine
    class Adapter:
        name="truth_official_timeline"
        last_status="ACCESS_DENIED"
        last_observations=[]
        def collect(self,start,end): return []
    class Fallback:
        name="truth_search_index"
        last_status="SUCCESS:1"
        last_observations=[]
        def collect(self,start,end):
            from trump_monitor.models import RawItem
            return [RawItem(raw_item_id="x",source_name="Truth Search Index",publisher_group="Truth Search Index",source_type="UNCONFIRMED",published_at=end,title="Trump policy update",body="Trump policy update",url="https://example.com",source_confidence=.4,direct_quote=False,source_tier=4,source_role="SUPPLEMENT",acquisition_method="SEARCH_INDEX_SNIPPET")]
    result=TrumpEventEngine(AppConfig(mode="ONLINE"),[Adapter(),Fallback()]).run(datetime.now(timezone.utc))
    assert "OFFICIAL_TIMELINE_UNAVAILABLE:ACCESS_DENIED" in result.truth_social_status
    assert "NO_POSTS" not in result.truth_social_status
