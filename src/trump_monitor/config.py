from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import yaml


@dataclass(frozen=True)
class AppConfig:
    title: str = "川普 72 小時事件監控與 GTC 整合"
    timezone: str = "Asia/Taipei"
    lookback_hours: int = 72
    mode: str = "AUTO"
    output_dir: str = "output"
    schema_version: str = "gtc.trump_event.v1.2"
    rule_weight: float = 0.7
    ai_weight: float = 0.3
    buy_ready_confidence: float = 0.8
    buy_ready_abs_score: int = 3
    truth_account: str = "realDonaldTrump"
    truth_profile_url: str = "https://truthsocial.com/@realDonaldTrump"
    truth_api_base_url: str = ""
    truth_manual_import_path: str = "data/truth_manual_posts.json"
    truth_official_timeline_enabled: bool = True
    truth_official_timeline_timeout: int = 20
    truth_official_timeline_max_pages: int = 8

    @property
    def sample_mode(self) -> bool:
        return self.mode.upper() == "SAMPLE"


def load_config(path: str | Path = "config.yaml") -> AppConfig:
    cfg_path = Path(path)
    data = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) if cfg_path.exists() else {}
    data = data or {}
    app, scoring, export, sources = data.get("app", {}), data.get("scoring", {}), data.get("export", {}), data.get("sources", {})
    truth = sources.get("truth_social", {})
    mode = str(app.get("mode", "AUTO")).upper()
    if mode not in {"AUTO", "ONLINE", "SAMPLE"}: mode = "AUTO"
    return AppConfig(
        title=app.get("title", AppConfig.title), timezone=app.get("timezone", AppConfig.timezone),
        lookback_hours=int(app.get("lookback_hours", 72)), mode=mode,
        output_dir=export.get("output_dir", "output"), schema_version=export.get("schema_version", "gtc.trump_event.v1.2"),
        rule_weight=float(scoring.get("rule_weight", .7)), ai_weight=float(scoring.get("ai_weight", .3)),
        buy_ready_confidence=float(scoring.get("buy_ready_confidence", .8)), buy_ready_abs_score=int(scoring.get("buy_ready_abs_score", 3)),
        truth_account=str(truth.get("account", "realDonaldTrump")), truth_profile_url=str(truth.get("profile_url", "https://truthsocial.com/@realDonaldTrump")),
        truth_api_base_url=str(truth.get("api_base_url", "")), truth_manual_import_path=str(truth.get("manual_import_path", "data/truth_manual_posts.json")),
        truth_official_timeline_enabled=bool(truth.get("official_timeline_enabled", True)),
        truth_official_timeline_timeout=int(truth.get("official_timeline_timeout_seconds", 20)),
        truth_official_timeline_max_pages=int(truth.get("official_timeline_max_pages", 8)),
    )
