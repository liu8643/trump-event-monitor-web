from __future__ import annotations

from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field

SourceType = Literal["DIRECT_POST", "MEDIA_REPORT", "OFFICIAL_POLICY", "UNCONFIRMED", "COMMENTARY"]
SourceRole = Literal["PRIMARY", "VERIFICATION", "SUPPLEMENT", "MANUAL"]
BattleAction = Literal["BUY_READY", "WATCH", "REDUCE", "AVOID"]


class RawItem(BaseModel):
    raw_item_id: str
    source_name: str
    publisher_group: str
    source_type: SourceType
    published_at: datetime
    title: str
    body: str = ""
    url: str
    source_confidence: float = Field(ge=0, le=1, default=0.5)
    direct_quote: bool = False
    source_tier: int = Field(ge=1, le=4, default=4)
    source_role: SourceRole = "SUPPLEMENT"
    acquisition_method: str = "UNKNOWN"
    account_handle: str = ""
    content_status: str = "SNIPPET"
    ai_summary_zh: str = ""
    ai_sentiment: str = "中性"
    ai_provider: str = "RULE_EXTRACTIVE_V2"
    ai_summary_status: str = "EXTRACTIVE_SNIPPET"


class SourceObservation(BaseModel):
    source_key: str
    layer: str
    status: str
    url: str
    displayed_text: str = ""
    note: str = ""
    observed_at: datetime
    eligible_for_event_engine: bool = False
    evidence_quality: str = "NONE"


class EventScore(BaseModel):
    rule_score: float
    ai_score: float
    final_score: float
    confidence: float = Field(ge=0, le=1)
    importance: int = Field(ge=1, le=5)
    breakdown: dict[str, float] = Field(default_factory=dict)


class MarketImpact(BaseModel):
    asset: str
    rule_score: int = Field(ge=-5, le=5)
    ai_score: int = Field(ge=-5, le=5)
    final_score: int = Field(ge=-5, le=5)
    confidence: float = Field(ge=0, le=1)
    direction: str
    rationale: str
    beneficiary: str = ""
    negative: str = ""
    horizon: str = "1-5 個交易日"


class EventCluster(BaseModel):
    event_id: str
    topic: str
    category: str
    summary: str
    first_seen: datetime
    last_seen: datetime
    source_count: int
    sources: list[RawItem]
    score: EventScore
    impacts: list[MarketImpact]
    beneficiary_sectors: list[str] = Field(default_factory=list)
    negative_sectors: list[str] = Field(default_factory=list)
    battle_action: BattleAction = "WATCH"
    event_label: str = "GENERAL_EVENT"
    data_freshness: str = "CURRENT"
    primary_source_present: bool = False
    verification_source_count: int = 0
    materiality_score: int = Field(ge=0, le=100, default=0)
    materiality_level: str = "WATCH"
    is_material: bool = False
    taiwan_candidates: list[dict] = Field(default_factory=list)


class RunResult(BaseModel):
    run_id: str
    started_at: datetime
    completed_at: datetime
    lookback_hours: int
    timezone: str
    status: Literal["SUCCESS", "PARTIAL", "DATA_UNAVAILABLE", "SOURCE_FAILED", "CANCELLED"]
    rule_version: str
    prompt_version: str
    model_version: str
    schema_version: str
    source_status: dict[str, str]
    source_counts: dict[str, int] = Field(default_factory=dict)
    source_observations: list[SourceObservation] = Field(default_factory=list)
    source_priority: list[str] = Field(default_factory=list)
    data_mode: Literal["ONLINE", "SAMPLE"] = "ONLINE"
    truth_social_status: str = "NOT_CONFIGURED"
    events: list[EventCluster]
    warnings: list[str] = Field(default_factory=list)
    taiwan_candidates: list[dict] = Field(default_factory=list)
    watchlist_paths: list[str] = Field(default_factory=list)
