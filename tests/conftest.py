from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolate_translation_runtime(monkeypatch, tmp_path):
    """Keep translation tests deterministic and independent of execution order.

    V2.3.13 introduced provider circuit breakers as process-level runtime state.
    Those states are correct in production, but must not leak from one pytest case
    into another.  The default test environment also disables live outbound
    translation; translation-specific tests explicitly enable it and mock HTTP.
    """
    import trump_monitor.translation as tr

    monkeypatch.setenv("TRANSLATION_ENABLED", "false")
    monkeypatch.setenv("TRANSLATION_FALLBACK_PROVIDER", "OFF")
    monkeypatch.setenv("TRANSLATION_CACHE_PATH", str(tmp_path / "translation_cache.json"))

    with tr._CACHE_LOCK:
        tr._CACHE.clear()
    tr._CACHE_LOADED = True
    tr._GOOGLE_BLOCKED_UNTIL = 0.0
    tr._MYMEMORY_BLOCKED_UNTIL = 0.0
    tr._LAST_REQUEST_AT = 0.0

    yield

    with tr._CACHE_LOCK:
        tr._CACHE.clear()
    tr._GOOGLE_BLOCKED_UNTIL = 0.0
    tr._MYMEMORY_BLOCKED_UNTIL = 0.0
    tr._LAST_REQUEST_AT = 0.0
