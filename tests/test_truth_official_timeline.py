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
        "realDonaldTrump", account_id="", session=session, page_size=40, max_pages=2,
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


class DirectIdSession:
    def __init__(self): self.calls=[]
    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append((url, params))
        assert "/accounts/lookup" not in url
        return FakeResponse([
            {"id":"direct","created_at":"2026-07-30T03:00:00Z","content":"<p>Direct ID post</p>","url":"https://truthsocial.com/@realDonaldTrump/direct"}
        ])


def test_truth_official_timeline_uses_configured_account_id_without_lookup():
    session=DirectIdSession()
    collector=TruthTimelineCollector(
        "https://truthsocial.com/@realDonaldTrump?gsid=x",
        "realDonaldTrump", account_id="107780257626128497", session=session,
    )
    rows=collector.collect(
        datetime(2026,7,29,tzinfo=timezone.utc),
        datetime(2026,7,30,4,tzinfo=timezone.utc),
    )
    assert len(rows)==1
    assert session.calls[0][0].endswith("/api/v1/accounts/107780257626128497/statuses")


def test_truth_official_timeline_failure_identifies_status_endpoint():
    class ForbiddenSession:
        def get(self, url, params=None, headers=None, timeout=None):
            response=FakeResponse({}, status_code=403)
            response.headers={"server":"cloudflare","cf-ray":"abc"}
            return response
    collector=TruthTimelineCollector(account_id="107780257626128497", session=ForbiddenSession(), rendered_html_enabled=False)
    rows=collector.collect(datetime(2026,7,29,tzinfo=timezone.utc), datetime(2026,7,30,tzinfo=timezone.utc))
    assert rows == []
    assert any("ACCOUNT_STATUSES_ACCESS_DENIED/HTTP_403" in obs.status for obs in collector.last_observations)
    assert collector.last_status == "ACCESS_DENIED"
