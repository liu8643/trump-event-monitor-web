from __future__ import annotations

from datetime import datetime, timezone

from trump_monitor.clustering import cluster_items
from trump_monitor.collectors.gdelt import GdeltDocAdapter
from trump_monitor.config import AppConfig
from trump_monitor.engine import TrumpEventEngine
from trump_monitor.materiality import score_materiality
from trump_monitor.models import RawItem
from trump_monitor.scoring import score_event
from trump_monitor.translation import normalize_zh_tw


def _item(rid: str, title: str, publisher: str = "Reuters", tier: int = 2) -> RawItem:
    return RawItem(
        raw_item_id=rid,
        source_name=publisher,
        publisher_group=publisher,
        source_type="MEDIA_REPORT",
        published_at=datetime(2026, 8, 25, 3, tzinfo=timezone.utc),
        title=title,
        body="",
        url=f"https://example.com/{rid}",
        source_tier=tier,
        source_confidence=.90 if tier == 2 else .68,
        source_role="VERIFICATION" if tier == 2 else "SUPPLEMENT",
        acquisition_method="GOOGLE_NEWS_RSS",
    )


def test_canada_50pct_auto_tariff_is_one_event_family():
    rows = [
        _item("c", "Trump says U.S. will hike Canada auto tariffs to 50% as trade war escalates", "CNBC", 2),
        _item("r", "Trump threatens 50% tariffs on all cars and trucks from Canada amid trade fight", "Reuters", 2),
        _item("w", "Trump announces tariffs on Canadian vehicles, steel in escalation of trade war", "The Washington Post", 3),
        _item("g", "Trump announces new 50% tariff on Canadian cars, trucks and steel", "The Guardian", 3),
    ]
    cats = {x.raw_item_id: "關稅／國際貿易" for x in rows}
    groups = cluster_items(rows, cats)
    assert len(groups) == 1
    assert len(groups[0][1]) == 4


def test_formal_iran_sanctions_plan_is_material():
    rows = [_item("c", "Trump admin unveils anti-Iran global sanctions plan, signals China not exempt", "CNBC", 2)]
    category = "地緣政治／能源"
    score = score_event(rows, category)
    total, level, material = score_materiality(rows, category, score)
    assert total >= 65 and material is True


def test_supreme_court_mail_voting_ruling_can_cross_material_gate():
    rows = [
        _item("a", "Supreme Court sides with Trump administration on mail voting restrictions ahead of midterms", "AP News", 2),
        _item("r", "US Supreme Court hands a win to Trump over mail-in ballot restrictions", "Reuters", 2),
    ]
    category = "美國政治／選舉制度"
    score = score_event(rows, category)
    total, level, material = score_materiality(rows, category, score)
    assert total >= 65 and material is True


def test_one_opinion_row_does_not_penalize_policy_cluster():
    rows = [
        _item("r", "Trump imposes 50% tariff on Canadian cars", "Reuters", 2),
        _item("a", "Trump imposes 50% tariff on Canadian cars", "AP News", 2),
        _item("o", "Opinion | What Trump's 50% Canada car tariff means", "USA Today", 3),
    ]
    category = "關稅／國際貿易"
    score = score_event(rows, category)
    total, level, material = score_materiality(rows, category, score)
    assert total >= 65 and material is True


def test_gdelt_rate_limit_opens_persisted_circuit_and_next_run_skips(monkeypatch, tmp_path):
    monkeypatch.setenv("GDELT_RETRIES", "1")
    monkeypatch.setenv("GDELT_CACHE_PATH", str(tmp_path / "gdelt_articles.json"))
    monkeypatch.setenv("GDELT_CIRCUIT_SECONDS", "1800")
    calls = {"n": 0}

    class Resp:
        status_code = 429
        text = "Please limit requests to one every 5 seconds"
        headers = {}

    def fake_get(*args, **kwargs):
        calls["n"] += 1
        return Resp()

    monkeypatch.setattr("trump_monitor.collectors.gdelt.requests.get", fake_get)
    adapter = GdeltDocAdapter()
    start = datetime(2026, 8, 25, 2, tzinfo=timezone.utc)
    end = datetime(2026, 8, 25, 4, tzinfo=timezone.utc)
    assert adapter.collect(start, end) == []
    assert adapter.last_status.startswith("DEGRADED:CIRCUIT_OPEN_NO_CACHE")
    assert calls["n"] == 1

    adapter2 = GdeltDocAdapter()
    assert adapter2.collect(start, end) == []
    assert adapter2.last_status.startswith("DEGRADED:CIRCUIT_OPEN_NO_CACHE")
    assert calls["n"] == 1


def test_taiwan_terminology_normalizes_trump_name():
    assert normalize_zh_tw("特朗普政府宣布新政策") == "川普政府宣布新政策"


def test_engine_preserves_specific_hormuz_category_when_rule_ai_is_general(monkeypatch):
    class Adapter:
        name = "fake"
        last_status = ""
        last_observations = []
        def collect(self, start, end):
            return [_item("h", "Trump claims Hormuz on Truth Social, Rezaei says shut until US changes", "Euronews", 3)]

    monkeypatch.setenv("TRANSLATION_ENABLED", "false")
    result = TrumpEventEngine(AppConfig(mode="ONLINE"), [Adapter()]).run(datetime(2026, 8, 25, 4, tzinfo=timezone.utc))
    assert result.events[0].category == "地緣政治／能源"
