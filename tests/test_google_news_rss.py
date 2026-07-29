from datetime import datetime, timezone
from trump_monitor.collectors.google_news_rss import GoogleNewsRssAdapter

RSS = b'''<?xml version="1.0"?><rss><channel><item>
<title>Trump announces policy - Reuters</title>
<link>https://news.google.com/rss/articles/abc</link>
<pubDate>Tue, 28 Jul 2026 01:00:00 GMT</pubDate>
<description><![CDATA[<a>Trump announces policy</a>]]></description>
<source url="https://reuters.com">Reuters</source>
</item></channel></rss>'''

class Response:
    status_code = 200
    content = RSS


def test_google_news_rss_parses_real_feed_shape(monkeypatch):
    monkeypatch.setattr("requests.get", lambda *a, **k: Response())
    rows = GoogleNewsRssAdapter().collect(
        datetime(2026,7,27,tzinfo=timezone.utc),
        datetime(2026,7,29,tzinfo=timezone.utc),
    )
    assert len(rows) == 1
    assert rows[0].source_name == "Reuters"
    assert rows[0].source_type == "MEDIA_REPORT"
