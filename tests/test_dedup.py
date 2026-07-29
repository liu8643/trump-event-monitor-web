from datetime import datetime, timezone
from trump_monitor.models import RawItem
from trump_monitor.dedup import canonicalize_url, deduplicate


def item(i, url, title):
    return RawItem(raw_item_id=i,source_name="X",publisher_group="X",source_type="MEDIA_REPORT",published_at=datetime.now(timezone.utc),title=title,url=url)


def test_canonicalize_tracking():
    assert canonicalize_url("https://EXAMPLE.com/a/?utm_source=x&b=2") == "https://example.com/a?b=2"


def test_exact_url_dedup():
    rows=[item("1","https://example.com/a?utm_source=x","hello"),item("2","https://example.com/a","other")]
    unique, dup=deduplicate(rows)
    assert len(unique)==1
    assert dup["2"]=="1"
