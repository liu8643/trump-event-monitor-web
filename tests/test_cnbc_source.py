from datetime import datetime, timezone
from trump_monitor.collectors.cnbc import CnbcNewsAdapter
from trump_monitor.collectors.source_policy import publisher_tier

RSS = b'''<?xml version="1.0"?><rss><channel>
<item><title>Trump markets update - CNBC</title><link>https://news.google.com/rss/articles/cnbc1</link><pubDate>Wed, 29 Jul 2026 15:00:00 GMT</pubDate><description><![CDATA[<a>CNBC report</a>]]></description><source url="https://www.cnbc.com">CNBC</source></item>
<item><title>Other report</title><link>https://news.google.com/rss/articles/other</link><pubDate>Wed, 29 Jul 2026 15:00:00 GMT</pubDate><description>Other</description><source url="https://example.com">Other</source></item>
</channel></rss>'''

class Response:
    status_code=200
    content=RSS

def test_cnbc_adapter_is_explicit_and_filters_other_publishers(monkeypatch):
    monkeypatch.setattr('requests.get', lambda *a, **k: Response())
    rows=CnbcNewsAdapter().collect(datetime(2026,7,29,tzinfo=timezone.utc),datetime(2026,7,30,tzinfo=timezone.utc))
    assert len(rows)==1
    assert rows[0].source_name=='CNBC'
    assert rows[0].acquisition_method=='CNBC_GOOGLE_NEWS_RSS'
    assert rows[0].source_tier==2 and rows[0].source_role=='VERIFICATION'

def test_cnbc_publisher_is_verification():
    assert publisher_tier('CNBC') == (2,'VERIFICATION')
