from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from trump_monitor.classifier import classify_category, classify_source_type
from trump_monitor.config import AppConfig
from trump_monitor.dedup import deduplicate
from trump_monitor.impact import build_impacts
from trump_monitor.models import EventCluster, RunResult, RawItem
from trump_monitor.scoring import score_event
from trump_monitor.collectors.source_policy import SOURCE_PRIORITY_LABELS
from trump_monitor.ai_service import analyze
from trump_monitor.taiwan_stocks import rank_candidates


class TrumpEventEngine:
    def __init__(self, config: AppConfig, adapters: list): self.config, self.adapters = config, adapters

    def run(self, now: datetime | None = None) -> RunResult:
        started=now or datetime.now(timezone.utc)
        if started.tzinfo is None: started=started.replace(tzinfo=timezone.utc)
        start=started-timedelta(hours=self.config.lookback_hours)
        raw=[]; source_status={}; source_counts={}; warnings=[]
        for adapter in self.adapters:
            try:
                rows=adapter.collect(start,started); raw.extend(rows); source_counts[adapter.name]=len(rows); source_status[adapter.name]=f"SUCCESS:{len(rows)}"
            except Exception as exc:
                source_counts[adapter.name]=0; source_status[adapter.name]=f"FAILED:{type(exc).__name__}"; warnings.append(f"{adapter.name}: {exc}")
        unique,_=deduplicate(raw); grouped=defaultdict(list)
        for item in unique:
            item.source_type=classify_source_type(item)  # type: ignore[misc]
            ai=analyze(item.title,item.body)
            item.ai_summary_zh=ai.summary_zh; item.ai_sentiment=ai.sentiment; item.ai_provider=ai.provider; item.ai_summary_status=ai.summary_status
            if item.acquisition_method in {"LICENSED_API", "MANUAL_IMPORT"} and item.body:
                item.content_status="FULL_OR_LICENSED"
            elif item.body:
                item.content_status="SNIPPET_OR_FEED_SUMMARY"
            grouped[ai.category or classify_category(item)].append(item)
        events=[]
        for idx,(category,items) in enumerate(grouped.items(),1):
            score=score_event(items,category); impacts=build_impacts(category,score)
            # Primary Truth Social first, then verification media, then supplemental sources.
            ordered=sorted(items,key=lambda x:(x.source_tier,-x.source_confidence,-x.published_at.timestamp()))
            top=ordered[0]
            event_id=f"TRUMP-{started.astimezone(ZoneInfo(self.config.timezone)):%Y%m%d}-{idx:03d}"
            action="REDUCE" if score.final_score<=-3 and score.confidence>=.8 else "WATCH"
            beneficiary=sorted({x for i in impacts for x in i.beneficiary.split("、") if x}); negative=sorted({x for i in impacts for x in i.negative.split("、") if x})
            summary=top.ai_summary_zh or (top.body or top.title)[:500]
            events.append(EventCluster(event_id=event_id,topic=top.title,category=category,summary=summary,
                first_seen=min(x.published_at for x in items),last_seen=max(x.published_at for x in items),source_count=len({x.publisher_group for x in items}),
                sources=ordered,score=score,impacts=impacts,beneficiary_sectors=beneficiary,negative_sectors=negative,battle_action=action,
                event_label=category.replace("／","_").replace(" ","_").upper(),data_freshness="SAMPLE" if self.config.sample_mode else "CURRENT",
                primary_source_present=any(x.source_tier==1 for x in items),verification_source_count=len({x.publisher_group for x in items if x.source_tier==2})))
        events.sort(key=lambda e:(e.score.importance,e.primary_source_present,e.verification_source_count,e.score.confidence,e.last_seen),reverse=True)
        candidates=rank_candidates(events)
        for e in events: e.taiwan_candidates=[x for x in candidates if e.event_id in x.get("reasons","")][:10]
        status="SUCCESS" if events and not warnings else "PARTIAL" if events else ("SOURCE_FAILED" if warnings else "DATA_UNAVAILABLE")
        truth_sources={k:v for k,v in source_status.items() if k.startswith("truth_")}
        official_count=source_counts.get("truth_official_timeline",0)
        fallback_count=sum(source_counts.get(k,0) for k in truth_sources if k != "truth_official_timeline")
        official_state=source_status.get("truth_official_timeline","NOT_CONFIGURED")
        if official_count:
            truth_status=f"OFFICIAL_TIMELINE_SUCCESS:{official_count};FALLBACK:{fallback_count}"
        elif official_state.startswith("FAILED"):
            truth_status=f"OFFICIAL_TIMELINE_FAILED;FALLBACK:{fallback_count}"
        elif fallback_count:
            truth_status=f"OFFICIAL_TIMELINE_NO_POSTS;FALLBACK:{fallback_count}"
        else:
            truth_status="NO_POSTS_IN_WINDOW"
        return RunResult(run_id=f"TRUMP-RUN-{started.astimezone(ZoneInfo(self.config.timezone)):%Y%m%d-%H%M%S}",started_at=started,
            completed_at=datetime.now(timezone.utc),lookback_hours=self.config.lookback_hours,timezone=self.config.timezone,status=status,
            rule_version="TRUMP_RULE_V2.2",prompt_version="TRUMP_PROMPT_V2.2",model_version="TRUTH_OFFICIAL_TIMELINE_V2.2",schema_version=self.config.schema_version,
            source_status=source_status,source_counts=source_counts,source_priority=SOURCE_PRIORITY_LABELS,data_mode="SAMPLE" if self.config.sample_mode else "ONLINE",
            truth_social_status=truth_status,events=events,warnings=warnings,taiwan_candidates=candidates,watchlist_paths=[])
