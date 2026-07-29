from datetime import datetime, timezone
from trump_monitor.config import AppConfig
from trump_monitor.engine import TrumpEventEngine
from trump_monitor.collectors.base import SourceAdapter, SourceError


class FailedAdapter(SourceAdapter):
    name = "failed_real_source"
    def collect(self, start, end):
        raise SourceError("network unavailable")


def test_online_failure_never_falls_back_to_sample():
    result = TrumpEventEngine(AppConfig(mode="AUTO"), [FailedAdapter()]).run(datetime(2026, 7, 28, tzinfo=timezone.utc))
    assert result.data_mode == "ONLINE"
    assert result.status == "SOURCE_FAILED"
    assert result.events == []
    assert "sample" not in result.source_status
