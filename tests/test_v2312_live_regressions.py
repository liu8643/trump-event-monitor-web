from __future__ import annotations
from datetime import datetime, timezone

from trump_monitor.collectors.gdelt import GdeltDocAdapter
import trump_monitor.translation as tr


def test_google_batch_translation_reduces_requests(monkeypatch, tmp_path):
    tr._CACHE.clear(); tr._CACHE_LOADED=True
    monkeypatch.setenv("TRANSLATION_ENABLED","true")
    monkeypatch.setenv("TRANSLATION_PROVIDER","GOOGLE_WEB")
    monkeypatch.setenv("TRANSLATION_BATCH_SIZE","8")
    monkeypatch.setenv("TRANSLATION_RETRIES","1")
    monkeypatch.setenv("TRANSLATION_RATE_LIMIT_SECONDS","0")
    monkeypatch.setenv("TRANSLATION_BATCH_PAUSE_SECONDS","0")
    monkeypatch.setenv("TRANSLATION_CACHE_PATH",str(tmp_path/"cache.json"))
    calls={"n":0}
    class Resp:
        status_code=200; headers={}
        def raise_for_status(self): return None
        def json(self):
            text='[[TMEISSEG000]] 川普宣布關稅\n[[TMEISSEG001]] 川普談伊朗'
            return [[[text,"x",None,None]]]
    def fake_get(*a,**k): calls["n"]+=1; return Resp()
    monkeypatch.setattr(tr.requests,"get",fake_get)
    out=tr.translate_many(["Trump announces tariffs","Trump talks Iran"])
    assert calls["n"]==1
    assert out["Trump announces tariffs"].text_zh=="川普宣布關稅"
    assert out["Trump talks Iran"].text_zh=="川普談伊朗"


def test_gdelt_429_retries_after_required_gap(monkeypatch, tmp_path):
    monkeypatch.setenv("GDELT_RETRIES","2")
    monkeypatch.setenv("GDELT_RETRY_SECONDS","5.2")
    monkeypatch.setenv("GDELT_CACHE_PATH",str(tmp_path/"g.json"))
    calls={"n":0}; sleeps=[]
    class Resp:
        headers={}; text="limit"
        def __init__(self,code): self.status_code=code
        def json(self):
            return {"articles":[{"url":"https://reuters.example/x","title":"Trump update","seendate":"20260825T000000Z","domain":"reuters.com"}]}
    def fake_get(*a,**k):
        calls["n"]+=1
        return Resp(429 if calls["n"]==1 else 200)
    monkeypatch.setattr("trump_monitor.collectors.gdelt.requests.get",fake_get)
    monkeypatch.setattr("trump_monitor.collectors.gdelt.time.sleep",lambda x:sleeps.append(x))
    rows=GdeltDocAdapter().collect(datetime(2026,8,24,tzinfo=timezone.utc),datetime(2026,8,25,1,tzinfo=timezone.utc))
    assert len(rows)==1 and calls["n"]==2
    assert sleeps and sleeps[0]>=5.2


def test_gdelt_uses_cached_direct_urls_after_live_429(monkeypatch, tmp_path):
    cache=tmp_path/"g.json"
    cache.write_text('{"articles":[{"url":"https://apnews.example/story","title":"Trump cached update","seendate":"20260825T000000Z","domain":"apnews.com"}]}',encoding="utf-8")
    monkeypatch.setenv("GDELT_RETRIES","1")
    monkeypatch.setenv("GDELT_CACHE_PATH",str(cache))
    class Resp:
        status_code=429; text="limit"; headers={}
    monkeypatch.setattr("trump_monitor.collectors.gdelt.requests.get",lambda *a,**k: Resp())
    adapter=GdeltDocAdapter()
    rows=adapter.collect(datetime(2026,8,24,tzinfo=timezone.utc),datetime(2026,8,25,1,tzinfo=timezone.utc))
    assert rows and rows[0].acquisition_method=="GDELT_DOC_API_DIRECT_URL_CACHE"
    assert adapter.last_status.startswith("SUCCESS_CACHE")

from trump_monitor.classifier import classify_category
from trump_monitor.materiality import score_materiality
from trump_monitor.scoring import score_event
from trump_monitor.models import RawItem


def _live_item(rid,title,publisher="Reuters",tier=2):
    return RawItem(raw_item_id=rid,source_name=publisher,publisher_group=publisher,source_type="MEDIA_REPORT",published_at=datetime(2026,8,24,tzinfo=timezone.utc),title=title,url=f"https://example.com/{rid}",source_tier=tier,source_confidence=.9 if tier==2 else .68,source_role="VERIFICATION" if tier==2 else "SUPPLEMENT",acquisition_method="GOOGLE_NEWS_RSS")


def test_poll_about_war_is_not_promoted_like_new_military_action():
    items=[_live_item("r","Trump's approval holds at record low as US support for Iran war falls, Reuters Ipsos poll finds"),_live_item("a","US public support for Iran war falls as Trump approval at record low: Poll","Al Jazeera",3)]
    cat="地緣政治／能源"
    score=score_event(items,cat)
    total,level,material=score_materiality(items,cat,score)
    assert total < 65 and material is False


def test_personal_stock_gain_story_routes_to_ethics_not_geopolitical():
    item=_live_item("c","Trump’s oil and gas stocks gained up to $15.5 million amid Iran war, congressional Democrats say","CNBC",2)
    assert classify_category(item)=="法律／監管／倫理"


def test_actual_tariff_action_remains_material():
    items=[_live_item("c","Trump says U.S. will hike Canada auto tariffs to 50% as trade war escalates","CNBC",2),_live_item("r","Trump threatens 50% tariffs on all cars and trucks from Canada amid trade fight","Reuters",2)]
    cat="關稅／國際貿易"
    score=score_event(items,cat)
    total,level,material=score_materiality(items,cat,score)
    assert total >= 65 and material is True
