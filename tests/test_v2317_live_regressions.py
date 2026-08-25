from __future__ import annotations
from datetime import datetime, timezone
import trump_monitor.translation as tr
from trump_monitor.collectors.gdelt import GdeltDocAdapter


def test_all_network_translation_failures_get_offline_chinese(monkeypatch):
    monkeypatch.setenv("TRANSLATION_ENABLED","true")
    monkeypatch.setenv("TRANSLATION_PROVIDER","GOOGLE_WEB")
    monkeypatch.setenv("TRANSLATION_FALLBACK_PROVIDER","MYMEMORY,LINGVA")
    monkeypatch.setattr(tr,"_translate_google_web_batch",lambda texts:{t:tr.TranslationResult("","GOOGLE_WEB_BATCH_UNOFFICIAL","FAILED:HTTP_429:CIRCUIT_OPEN") for t in texts})
    monkeypatch.setattr(tr,"_google_circuit_open",lambda:True)
    monkeypatch.setattr(tr,"_translate_mymemory_batch",lambda texts:{t:tr.TranslationResult("","MYMEMORY_PUBLIC","FAILED:CIRCUIT_OPEN") for t in texts})
    monkeypatch.setattr(tr,"_mymemory_circuit_open",lambda:True)
    monkeypatch.setattr(tr,"_translate_lingva_batch",lambda texts:{t:tr.TranslationResult("","LINGVA_PUBLIC","FAILED:TIMEOUT:CIRCUIT_OPEN") for t in texts})
    monkeypatch.setattr(tr,"_lingva_circuit_open",lambda:True)
    out=tr.translate_many(["Trump says U.S. will hike Canada auto tariffs to 50% as trade war escalates"])
    r=next(iter(out.values()))
    assert r.text_zh
    assert "川普" in r.text_zh and "50%" in r.text_zh
    assert r.provider=="LOCAL_RULE_ZH_TW"
    assert r.status.startswith("SUCCESS:LOCAL_RULE_PARTIAL")


def test_local_rule_covers_scotus_mail_vote():
    r=tr._translate_local_rule("Supreme Court sides with Trump administration on mail voting restrictions ahead of midterms")
    assert "最高法院" in r.text_zh and "郵寄投票" in r.text_zh


def test_local_rule_covers_iran_sanctions():
    r=tr._translate_local_rule("Trump admin unveils anti-Iran global sanctions plan, signals China not exempt")
    assert "伊朗" in r.text_zh and "制裁" in r.text_zh


def test_gdelt_timeout_is_degraded_not_exception(monkeypatch,tmp_path):
    monkeypatch.setenv("GDELT_RETRIES","1")
    monkeypatch.setenv("GDELT_CACHE_PATH",str(tmp_path/"g.json"))
    monkeypatch.setenv("GDELT_STATE_PATH",str(tmp_path/"state.json"))
    import requests
    monkeypatch.setattr("trump_monitor.collectors.gdelt.requests.get",lambda *a,**k: (_ for _ in ()).throw(requests.ReadTimeout("x")))
    a=GdeltDocAdapter(timeout=1)
    rows=a.collect(datetime(2026,8,25,tzinfo=timezone.utc),datetime(2026,8,26,tzinfo=timezone.utc))
    assert rows==[]
    assert a.last_status.startswith("DEGRADED:CIRCUIT_OPEN_NO_CACHE")


def test_local_rule_generic_is_explicitly_partial():
    r=tr._translate_local_rule("Trump discusses a new policy with governors")
    assert r.text_zh.startswith("【規則式繁中摘要】")
    assert r.status.startswith("SUCCESS:LOCAL_RULE_PARTIAL")
