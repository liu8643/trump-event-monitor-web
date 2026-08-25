from __future__ import annotations

from datetime import datetime, timezone

from trump_monitor.collectors.federal_register import FederalRegisterAdapter
from trump_monitor.collectors.treasury import TreasuryOfficialAdapter
from trump_monitor.config import AppConfig
from trump_monitor.translation import translate_many


def test_google_and_mymemory_throttled_can_fall_to_lingva(monkeypatch):
    monkeypatch.setenv("TRANSLATION_ENABLED", "true")
    monkeypatch.setenv("TRANSLATION_PROVIDER", "GOOGLE_WEB")
    monkeypatch.setenv("TRANSLATION_FALLBACK_PROVIDER", "MYMEMORY,LINGVA")
    monkeypatch.setenv("TRANSLATION_BATCH_PAUSE_SECONDS", "0")
    monkeypatch.setenv("TRANSLATION_RATE_LIMIT_SECONDS", "0")
    monkeypatch.setenv("TRANSLATION_MYMEMORY_RATE_LIMIT_SECONDS", "0")
    monkeypatch.setenv("TRANSLATION_LINGVA_RATE_LIMIT_SECONDS", "0")

    import trump_monitor.translation as tr
    monkeypatch.setattr(tr, "_translate_google_web_batch", lambda texts: {t: tr.TranslationResult("", "GOOGLE_WEB_BATCH_UNOFFICIAL", "FAILED:HTTP_429:CIRCUIT_OPEN") for t in texts})
    monkeypatch.setattr(tr, "_google_circuit_open", lambda: True)
    monkeypatch.setattr(tr, "_translate_mymemory_batch", lambda texts: {t: tr.TranslationResult("", "MYMEMORY_PUBLIC", "FAILED:HTTP_429:CIRCUIT_OPEN") for t in texts})
    monkeypatch.setattr(tr, "_mymemory_circuit_open", lambda: True)
    monkeypatch.setattr(tr, "_translate_lingva_batch", lambda texts: {t: tr.TranslationResult("川普宣布新政策", "LINGVA_PUBLIC", "SUCCESS") for t in texts})
    monkeypatch.setattr(tr, "_lingva_circuit_open", lambda: False)

    out = translate_many(["Trump announces new policy"])
    assert out["Trump announces new policy"].text_zh == "川普宣布新政策"
    assert out["Trump announces new policy"].provider == "LINGVA_PUBLIC"


def test_config_disables_rendered_browser_by_default():
    assert AppConfig().truth_rendered_html_enabled is False


def test_federal_register_parser_returns_official_direct_url(monkeypatch):
    class Resp:
        status_code = 200
        def raise_for_status(self): return None
        def json(self):
            return {"results": [{"title": "Presidential action on tariffs", "html_url": "https://www.federalregister.gov/documents/2026/08/25/example", "publication_date": "2026-08-25", "abstract": "Official action"}]}
    monkeypatch.setattr("trump_monitor.collectors.federal_register.requests.get", lambda *a, **k: Resp())
    rows = FederalRegisterAdapter().collect(datetime(2026,8,24,tzinfo=timezone.utc), datetime(2026,8,26,tzinfo=timezone.utc))
    assert len(rows) == 1
    assert rows[0].source_tier == 1 and rows[0].source_role == "PRIMARY"
    assert rows[0].acquisition_method == "FEDERAL_REGISTER_API_DIRECT_URL"


def test_treasury_parser_returns_official_direct_url(monkeypatch):
    page = b'<html><body><div><span>August 25, 2026</span><a href="/news/press-releases/jy9999">Treasury Announces New Iran Sanctions Action</a></div></body></html>'
    class Resp:
        content = page
        def raise_for_status(self): return None
    monkeypatch.setattr("trump_monitor.collectors.treasury.requests.get", lambda *a, **k: Resp())
    rows = TreasuryOfficialAdapter().collect(datetime(2026,8,24,tzinfo=timezone.utc), datetime(2026,8,26,tzinfo=timezone.utc))
    assert len(rows) == 1
    assert rows[0].url.startswith("https://home.treasury.gov/")
    assert rows[0].source_tier == 1


def test_lingva_public_result_is_validated_and_taiwan_normalized(monkeypatch):
    import trump_monitor.translation as tr
    monkeypatch.setattr(tr, "_lingva_instances", lambda: ["https://example.invalid"])
    monkeypatch.setenv("TRANSLATION_LINGVA_RATE_LIMIT_SECONDS", "0")
    class Resp:
        status_code = 200
        def raise_for_status(self): return None
        def json(self): return {"translation": "特朗普宣布新關稅"}
    monkeypatch.setattr(tr.requests, "get", lambda *a, **k: Resp())
    result = tr._translate_lingva_batch(["Trump announces new tariff"])["Trump announces new tariff"]
    assert result.text_zh == "川普宣布新關稅"
    assert result.status == "SUCCESS"
