from __future__ import annotations

from datetime import datetime, timezone

from trump_monitor.collectors.gdelt import GdeltDocAdapter
from trump_monitor.collectors.whitehouse import WhiteHouseOfficialAdapter
from trump_monitor.dedup import deduplicate
from trump_monitor.models import RawItem
from trump_monitor.translation import translate_text


def raw(rid, publisher, title, url, acquisition="GOOGLE_NEWS_RSS", tier=3):
    return RawItem(raw_item_id=rid,source_name=publisher,publisher_group=publisher,source_type="MEDIA_REPORT",published_at=datetime(2026,8,24,tzinfo=timezone.utc),title=title,url=url,source_tier=tier,acquisition_method=acquisition)


def test_dedup_preserves_cross_publisher_corroboration():
    a=raw("r","Reuters","Trump announces tariff plan","https://r.example/a",tier=2)
    b=raw("ap","AP News","Trump announces tariff plan","https://ap.example/b",tier=2)
    unique,_=deduplicate([a,b])
    assert len(unique)==2


def test_dedup_prefers_direct_url_within_same_publisher():
    g=raw("g","Reuters","Trump announces tariff plan - Reuters","https://news.google.com/rss/articles/x","GOOGLE_NEWS_RSS",2)
    d=raw("d","Reuters","Trump announces tariff plan - Reuters","https://reuters.com/world/a","GDELT_DOC_API_DIRECT_URL",2)
    unique,_=deduplicate([g,d])
    assert len(unique)==1
    assert unique[0].url.startswith("https://reuters.com")


def test_translation_failure_not_persisted_in_memory_cache(monkeypatch, tmp_path):
    import trump_monitor.translation as tr
    tr._CACHE.clear(); tr._CACHE_LOADED=True
    monkeypatch.setenv("TRANSLATION_ENABLED","true")
    monkeypatch.setenv("TRANSLATION_PROVIDER","GOOGLE_WEB")
    monkeypatch.setenv("TRANSLATION_RETRIES","1")
    monkeypatch.setenv("TRANSLATION_RATE_LIMIT_SECONDS","0")
    monkeypatch.setenv("TRANSLATION_CACHE_PATH",str(tmp_path/"cache.json"))
    calls={"n":0}
    class Resp:
        status_code=200; headers={}
        def raise_for_status(self): return None
        def json(self):
            calls["n"]+=1
            if calls["n"]<=2: raise ValueError("bad")
            return [[ ["川普宣布關稅方案","Trump announces tariff plan",None,None] ]]
    monkeypatch.setattr(tr.requests,"get",lambda *a,**k: Resp())
    first=translate_text("Trump announces tariff plan")
    second=translate_text("Trump announces tariff plan")
    assert first.text_zh and first.provider=="LOCAL_RULE_ZH_TW"
    assert first.status.startswith("SUCCESS:LOCAL_RULE_PARTIAL")
    # LOCAL partial must not be persisted: a later provider recovery can upgrade it.
    assert second.text_zh=="川普宣布關稅方案"
    assert second.provider=="GOOGLE_WEB_UNOFFICIAL"


def test_gdelt_returns_direct_publisher_url(monkeypatch):
    class Resp:
        status_code=200
        text=""
        def json(self):
            return {"articles":[{"url":"https://example.com/story","title":"Trump policy update","seendate":"20260824T120000Z","domain":"example.com"}]}
    monkeypatch.setattr("trump_monitor.collectors.gdelt.requests.get",lambda *a,**k: Resp())
    rows=GdeltDocAdapter().collect(datetime(2026,8,24,0,0,tzinfo=timezone.utc),datetime(2026,8,25,0,0,tzinfo=timezone.utc))
    assert len(rows)==1 and rows[0].url=="https://example.com/story"
    assert rows[0].acquisition_method=="GDELT_DOC_API_DIRECT_URL"


def test_whitehouse_public_page_direct_url(monkeypatch):
    html=b'''<html><body><article><h2><a href="/releases/2026/08/test/">President Trump Announces Test Policy</a></h2><time datetime="2026-08-24T10:00:00Z"></time></article></body></html>'''
    class Resp:
        status_code=200; content=html
    monkeypatch.setattr("trump_monitor.collectors.whitehouse.requests.get",lambda *a,**k: Resp())
    rows=WhiteHouseOfficialAdapter().collect(datetime(2026,8,24,0,0,tzinfo=timezone.utc),datetime(2026,8,25,0,0,tzinfo=timezone.utc))
    assert rows and rows[0].url=="https://www.whitehouse.gov/releases/2026/08/test/"
    assert rows[0].source_tier==1
