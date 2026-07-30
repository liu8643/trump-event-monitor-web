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
