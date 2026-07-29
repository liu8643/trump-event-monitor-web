from datetime import datetime, timezone
from trump_monitor.models import RawItem
from trump_monitor.scoring import score_event
from trump_monitor.collectors.source_policy import publisher_tier


def test_publisher_priority():
    assert publisher_tier("Reuters") == (2, "VERIFICATION")
    assert publisher_tier("Associated Press") == (2, "VERIFICATION")
    assert publisher_tier("Bloomberg") == (2, "VERIFICATION")
    assert publisher_tier("Other") == (3, "SUPPLEMENT")


def test_truth_primary_score_beats_media_only():
    now=datetime.now(timezone.utc)
    truth=RawItem(raw_item_id="t",source_name="Truth Social",publisher_group="Truth Social",source_type="DIRECT_POST",published_at=now,title="Iran tariff",url="https://truthsocial.com/x",source_confidence=.98,source_tier=1,source_role="PRIMARY",acquisition_method="LICENSED_API")
    reuters=RawItem(raw_item_id="r",source_name="Reuters",publisher_group="Reuters",source_type="MEDIA_REPORT",published_at=now,title="Iran tariff",url="https://reuters.com/x",source_confidence=.9,source_tier=2,source_role="VERIFICATION",acquisition_method="GOOGLE_NEWS_RSS")
    score=score_event([truth,reuters],"地緣政治／能源")
    assert score.breakdown["truth_primary"] == 3
    assert score.breakdown["verification_source"] == 2
    assert score.importance == 5
