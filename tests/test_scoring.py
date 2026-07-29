from datetime import datetime, timezone
from trump_monitor.models import RawItem
from trump_monitor.scoring import score_event


def test_score_direct_multi_source():
    rows=[
        RawItem(raw_item_id="1",source_name="Truth Social",publisher_group="Truth Social",source_type="DIRECT_POST",published_at=datetime.now(timezone.utc),title="Iran military",url="https://truthsocial.com/x",source_confidence=.9),
        RawItem(raw_item_id="2",source_name="Reuters",publisher_group="Reuters",source_type="MEDIA_REPORT",published_at=datetime.now(timezone.utc),title="Iran military",url="https://reuters.com/x",source_confidence=.9),
    ]
    score=score_event(rows,"地緣政治／能源")
    assert score.rule_score >= 6
    assert score.importance >= 4
    assert score.confidence >= .8
