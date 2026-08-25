from __future__ import annotations
from datetime import datetime, timezone

import trump_monitor.translation as tr
from trump_monitor.collectors.gdelt import GdeltDocAdapter
from trump_monitor.classifier import classify_category
from trump_monitor.models import RawItem


def _reset_translation(tmp_path, monkeypatch):
    tr._CACHE.clear(); tr._CACHE_LOADED=True
    tr._GOOGLE_BLOCKED_UNTIL=0.0; tr._MYMEMORY_BLOCKED_UNTIL=0.0
    monkeypatch.setenv("TRANSLATION_ENABLED","true")
    monkeypatch.setenv("TRANSLATION_PROVIDER","GOOGLE_WEB")
    monkeypatch.setenv("TRANSLATION_FALLBACK_PROVIDER","MYMEMORY")
    monkeypatch.setenv("TRANSLATION_RETRIES","1")
    monkeypatch.setenv("TRANSLATION_RATE_LIMIT_SECONDS","0")
    monkeypatch.setenv("TRANSLATION_MYMEMORY_RATE_LIMIT_SECONDS","0")
    monkeypatch.setenv("TRANSLATION_BATCH_PAUSE_SECONDS","0")
    monkeypatch.setenv("TRANSLATION_CACHE_PATH",str(tmp_path/"translation.json"))


def test_google_429_opens_circuit_and_falls_back_without_repeating_google(monkeypatch,tmp_path):
    _reset_translation(tmp_path,monkeypatch)
    calls={"google":0,"mm":0}
    class Resp:
        headers={}
        def __init__(self,code,payload=None): self.status_code=code; self._payload=payload or {}
        def raise_for_status(self):
            if self.status_code>=400:
                import requests
                r=requests.Response(); r.status_code=self.status_code
                raise requests.HTTPError(response=r)
        def json(self): return self._payload
    def fake_get(url,*a,**k):
        if "mymemory" in url:
            calls["mm"]+=1
            q=k["params"]["q"]
            if "MMEISSEG001" in q:
                text="[[MMEISSEG000]] 川普提高加拿大汽車關稅\n[[MMEISSEG001]] 美國最高法院郵寄投票裁決"
            else:
                text="[[MMEISSEG000]] 川普提高加拿大汽車關稅"
            return Resp(200,{"responseData":{"translatedText":text}})
        calls["google"]+=1
        return Resp(429)
    monkeypatch.setattr(tr.requests,"get",fake_get)
    out=tr.translate_many(["Trump hikes Canada auto tariffs","Supreme Court rules on mail voting"])
    assert calls["google"]==1
    assert calls["mm"]==1
    assert out["Trump hikes Canada auto tariffs"].text_zh
    assert out["Supreme Court rules on mail voting"].provider=="MYMEMORY_PUBLIC"


def test_google_circuit_skips_minutes_of_retries(monkeypatch,tmp_path):
    _reset_translation(tmp_path,monkeypatch)
    monkeypatch.setenv("TRANSLATION_FALLBACK_PROVIDER","OFF")
    calls={"n":0}
    class Resp:
        status_code=429; headers={}
    monkeypatch.setattr(tr.requests,"get",lambda *a,**k:(calls.__setitem__("n",calls["n"]+1) or Resp()))
    out=tr.translate_many([f"Headline {i}" for i in range(20)])
    assert calls["n"]==1
    assert all(x.text_zh for x in out.values())
    assert all(x.provider=="LOCAL_RULE_ZH_TW" for x in out.values())


def test_gdelt_http200_plaintext_rate_limit_retries_then_succeeds(monkeypatch,tmp_path):
    monkeypatch.setenv("GDELT_RETRIES","2")
    monkeypatch.setenv("GDELT_RETRY_SECONDS","5.2")
    monkeypatch.setenv("GDELT_CACHE_PATH",str(tmp_path/"gdelt.json"))
    calls={"n":0}; sleeps=[]
    class Resp:
        headers={"Content-Type":"text/plain"}
        status_code=200
        def __init__(self,plain): self.plain=plain; self.text="Please limit requests to one request every 5 seconds" if plain else "{}"
        def json(self):
            if self.plain: raise ValueError("not json")
            return {"articles":[{"url":"https://reuters.example/a","title":"Trump tariff update","seendate":"20260825T030000Z","domain":"reuters.com"}]}
    def fake_get(*a,**k):
        calls["n"]+=1; return Resp(calls["n"]==1)
    monkeypatch.setattr("trump_monitor.collectors.gdelt.requests.get",fake_get)
    monkeypatch.setattr("trump_monitor.collectors.gdelt.time.sleep",lambda x:sleeps.append(x))
    rows=GdeltDocAdapter().collect(datetime(2026,8,25,2,tzinfo=timezone.utc),datetime(2026,8,25,4,tzinfo=timezone.utc))
    assert len(rows)==1 and calls["n"]==2
    assert sleeps and sleeps[0]>=5.2


def test_gdelt_http200_nonjson_uses_cache_after_retries(monkeypatch,tmp_path):
    cache=tmp_path/"gdelt.json"
    cache.write_text('{"articles":[{"url":"https://apnews.example/a","title":"Trump update","seendate":"20260825T030000Z","domain":"apnews.com"}]}',encoding="utf-8")
    monkeypatch.setenv("GDELT_RETRIES","1")
    monkeypatch.setenv("GDELT_CACHE_PATH",str(cache))
    class Resp:
        status_code=200; headers={"Content-Type":"text/html"}; text="Service temporarily unavailable"
        def json(self): raise ValueError("html")
    monkeypatch.setattr("trump_monitor.collectors.gdelt.requests.get",lambda *a,**k:Resp())
    rows=GdeltDocAdapter().collect(datetime(2026,8,25,2,tzinfo=timezone.utc),datetime(2026,8,25,4,tzinfo=timezone.utc))
    assert rows and rows[0].acquisition_method=="GDELT_DOC_API_DIRECT_URL_CACHE"


def _item(title: str) -> RawItem:
    return RawItem(raw_item_id="x",source_name="AP News",publisher_group="AP News",source_type="MEDIA_REPORT",published_at=datetime(2026,8,25,tzinfo=timezone.utc),title=title,url="https://example.com/x",source_tier=2,source_confidence=.9,source_role="VERIFICATION",acquisition_method="GOOGLE_NEWS_RSS")


def test_deportation_story_is_immigration_not_trade():
    assert classify_category(_item("Wife of active-duty Army sergeant deported amid Trump's immigration campaign"))=="移民／邊境政策"


def test_h1b_fee_story_is_immigration_policy():
    assert classify_category(_item("Trump administration seeks to formalise H-1B fee of more than $100,000"))=="移民／邊境政策"
