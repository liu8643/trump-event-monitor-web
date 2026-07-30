from datetime import datetime, timezone

from trump_monitor.collectors.truth_social import TruthTimelineCollector


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self):
        self.calls = []

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append((url, params))
        if url.endswith("/api/v1/accounts/lookup"):
            return FakeResponse({"id": "acct-123", "acct": "realDonaldTrump"})
        return FakeResponse([
            {"id": "new", "created_at": "2026-07-30T03:00:00Z", "content": "<p>Newest public post</p>", "url": "https://truthsocial.com/@realDonaldTrump/posts/new"},
            {"id": "mid", "created_at": "2026-07-29T03:00:00Z", "content": "<p>Middle<br>post</p>", "url": "https://truthsocial.com/@realDonaldTrump/posts/mid"},
            {"id": "old", "created_at": "2026-07-25T03:00:00Z", "content": "<p>Too old</p>", "url": "https://truthsocial.com/@realDonaldTrump/posts/old"},
        ])


def test_truth_official_timeline_filters_sorts_and_marks_primary():
    session = FakeSession()
    collector = TruthTimelineCollector(
        "https://truthsocial.com/@realDonaldTrump?gsid=test",
        "realDonaldTrump", session=session, page_size=40, max_pages=2,
    )
    rows = collector.collect(
        datetime(2026, 7, 28, tzinfo=timezone.utc),
        datetime(2026, 7, 30, 4, tzinfo=timezone.utc),
    )
    assert [r.raw_item_id for r in rows] == ["TRUTH-TIMELINE-mid", "TRUTH-TIMELINE-new"]
    assert all(r.source_type == "DIRECT_POST" and r.source_tier == 1 for r in rows)
    assert all(r.source_role == "PRIMARY" and r.direct_quote for r in rows)
    assert rows[0].body == "Middle\npost"
    assert session.calls[0][0] == "https://truthsocial.com/api/v1/accounts/lookup"
    assert session.calls[1][0].endswith("/api/v1/accounts/acct-123/statuses")


def test_truth_official_timeline_profile_handle_fallback():
    collector = TruthTimelineCollector("https://truthsocial.com/@realDonaldTrump?gsid=x", account="")
    assert collector.account == "realDonaldTrump"
    assert collector.base_url == "https://truthsocial.com"
