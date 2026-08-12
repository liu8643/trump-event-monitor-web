from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from trump_monitor.models import EventCluster, EventScore, RawItem, RunResult
from trump_monitor.translation import TranslationResult, contains_cjk, translate_text


def test_contains_cjk_and_already_zh():
    assert contains_cjk("川普安全事件")
    r = translate_text("川普安全事件")
    assert r.text_zh == "川普安全事件"
    assert r.status == "ALREADY_ZH"


def test_google_translation_parse(monkeypatch):
    class Resp:
        def raise_for_status(self): return None
        def json(self): return [[["川普表示他的飛機面臨更大的風險", "Trump says his plane faced greater risk", None, None]]]
    monkeypatch.setenv("TRANSLATION_ENABLED", "true")
    monkeypatch.setenv("TRANSLATION_PROVIDER", "GOOGLE_WEB")
    monkeypatch.setattr("trump_monitor.translation.requests.get", lambda *a, **k: Resp())
    import trump_monitor.translation as tr
    tr._CACHE.clear()
    r = translate_text("Trump says his plane faced greater risk")
    assert r.text_zh == "川普表示他的飛機面臨更大的風險"
    assert r.status == "SUCCESS"


def test_bilingual_model_keeps_english_original():
    now=datetime(2026,8,12,tzinfo=timezone.utc)
    raw=RawItem(raw_item_id="1",source_name="Reuters",publisher_group="Reuters",source_type="MEDIA_REPORT",published_at=now,title="Trump says Iran options are severe",title_zh="川普表示對伊朗的選項相當嚴厲",url="https://example.com")
    e=EventCluster(event_id="E1",topic=raw.title,topic_zh=raw.title_zh,category="地緣政治／能源",summary="English summary",summary_zh="中文摘要",translation_status="TITLE:SUCCESS;SUMMARY:SUCCESS",first_seen=now,last_seen=now,source_count=1,sources=[raw],score=EventScore(rule_score=4,ai_score=0,final_score=4,confidence=.766,importance=3),impacts=[])
    assert e.topic.startswith("Trump")
    assert e.topic_zh.startswith("川普")
    assert e.summary == "English summary"
    assert e.summary_zh == "中文摘要"


def test_ui_confidence_uses_0_to_100_display():
    text=Path("app/streamlit_app.py").read_text(encoding="utf-8")
    assert 'round(e.score.confidence*100)' in text
    assert 'min_value=0,max_value=100,format="%d%%"' in text
    assert 'min_value=0,max_value=1,format="%.0f%%"' not in text
