from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from trump_monitor.classifier import classify_category, classify_source_type
from trump_monitor.clustering import cluster_items
from trump_monitor.config import AppConfig
from trump_monitor.dedup import deduplicate
from trump_monitor.impact import build_impacts
from trump_monitor.materiality import score_materiality
from trump_monitor.models import EventCluster, RunResult
from trump_monitor.scoring import score_event
from trump_monitor.collectors.source_policy import SOURCE_PRIORITY_LABELS
from trump_monitor.ai_service import analyze
from trump_monitor.taiwan_stocks import rank_candidates
from trump_monitor.logging_utils import get_logger, log_exception

logger = get_logger("engine")


class TrumpEventEngine:
    def __init__(self, config: AppConfig, adapters: list): self.config, self.adapters = config, adapters

    def run(self, now: datetime | None = None) -> RunResult:
        started=now or datetime.now(timezone.utc)
        if started.tzinfo is None: started=started.replace(tzinfo=timezone.utc)
        start=started-timedelta(hours=self.config.lookback_hours)
        logger.info("run start | mode=%s | lookback=%sh | adapters=%s", self.config.mode, self.config.lookback_hours, [a.name for a in self.adapters])
        raw=[]; source_status={}; source_counts={}; source_observations=[]; warnings=[]
        for adapter in self.adapters:
            try:
                rows=adapter.collect(start,started); raw.extend(rows); source_counts[adapter.name]=len(rows)
                adapter_state=getattr(adapter,"last_status","")
                source_status[adapter.name]=adapter_state or (f"SUCCESS:{len(rows)}" if rows else "NO_DATA:0")
                observations=getattr(adapter,"last_observations",[]) or []
                source_observations.extend(observations)
                logger.debug("adapter complete | %s | rows=%d | state=%s", adapter.name, len(rows), source_status[adapter.name])
                for obs in observations:
                    logger.debug("source observation | %s | layer=%s | status=%s | eligible=%s | quality=%s | note=%s", adapter.name, obs.layer, obs.status, obs.eligible_for_event_engine, obs.evidence_quality, " ".join(obs.note.split())[:240])
                if adapter_state and not adapter_state.startswith("SUCCESS") and adapter_state not in {"NO_POSTS_IN_72H","NO_DATA:0"}:
                    warnings.append(f"{adapter.name}: {adapter_state}")
                    logger.warning("source degraded | %s | state=%s", adapter.name, adapter_state)
            except Exception as exc:
                source_counts[adapter.name]=0
                detail=" ".join(str(exc).split())[:180] or type(exc).__name__
                source_status[adapter.name]=f"FAILED:{type(exc).__name__}:{detail}"
                warnings.append(f"{adapter.name}: {detail}")
                log_exception(logger, f"adapter failed | {adapter.name}", exc)

        unique,_=deduplicate(raw)
        categories: dict[str,str] = {}
        for item in unique:
            item.source_type=classify_source_type(item)  # type: ignore[misc]
            ai=analyze(item.title,item.body)
            item.ai_summary_zh=ai.summary_zh; item.ai_sentiment=ai.sentiment; item.ai_provider=ai.provider; item.ai_summary_status=ai.summary_status
            if item.acquisition_method in {"LICENSED_API", "MANUAL_IMPORT"} and item.body:
                item.content_status="FULL_OR_LICENSED"
            elif item.body:
                item.content_status="SNIPPET_OR_FEED_SUMMARY"
            # Guardrail categories are deterministic for safety/health/security false-positive cases.
            deterministic=classify_category(item)
            if deterministic in {"醫療／社會政策", "總統安全／國安"}:
                category=deterministic
            else:
                category=ai.category or deterministic
            categories[item.raw_item_id]=category

        grouped=cluster_items(unique,categories)
        logger.info("event clustering | raw=%d | unique=%d | clusters=%d", len(raw), len(unique), len(grouped))
        events=[]
        for idx,(category,items) in enumerate(grouped,1):
            score=score_event(items,category); impacts=build_impacts(category,score)
            ordered=sorted(items,key=lambda x:(x.source_tier,-x.source_confidence,-x.published_at.timestamp()))
            top=ordered[0]
            event_id=f"TRUMP-{started.astimezone(ZoneInfo(self.config.timezone)):%Y%m%d}-{idx:03d}"
            action="REDUCE" if score.final_score<=-3 and score.confidence>=.8 else "WATCH"
            beneficiary=sorted({x for i in impacts for x in i.beneficiary.split("、") if x}); negative=sorted({x for i in impacts for x in i.negative.split("、") if x})
            summary=top.ai_summary_zh or (top.body or top.title)[:500]
            materiality_score, materiality_level, is_material = score_materiality(items, category, score)
            events.append(EventCluster(event_id=event_id,topic=top.title,category=category,summary=summary,
                first_seen=min(x.published_at for x in items),last_seen=max(x.published_at for x in items),source_count=len({x.publisher_group for x in items}),
                sources=ordered,score=score,impacts=impacts,beneficiary_sectors=beneficiary,negative_sectors=negative,battle_action=action,
                event_label=category.replace("／","_").replace(" ","_").upper(),data_freshness="SAMPLE" if self.config.sample_mode else "CURRENT",
                primary_source_present=any(x.source_tier==1 for x in items),verification_source_count=len({x.publisher_group for x in items if x.source_tier==2}),
                materiality_score=materiality_score,materiality_level=materiality_level,is_material=is_material))
        events.sort(key=lambda e:(e.is_material,e.materiality_score,e.score.importance,e.primary_source_present,e.verification_source_count,e.score.confidence,e.last_seen),reverse=True)
        material_events=[e for e in events if e.is_material]
        candidates=rank_candidates(material_events)
        for e in events: e.taiwan_candidates=[x for x in candidates if e.event_id in x.get("reasons","")][:10]
        status="SUCCESS" if events and not warnings else "PARTIAL" if events else ("SOURCE_FAILED" if warnings else "DATA_UNAVAILABLE")
        truth_sources={k:v for k,v in source_status.items() if k.startswith("truth_")}
        official_count=source_counts.get("truth_official_timeline",0)
        fallback_count=sum(source_counts.get(k,0) for k in truth_sources if k != "truth_official_timeline")
        official_state=source_status.get("truth_official_timeline","NOT_CONFIGURED")
        if official_count:
            truth_status=f"OFFICIAL_TIMELINE_SUCCESS:{official_count};FALLBACK:{fallback_count}"
        elif official_state.startswith("FAILED"):
            truth_status=f"OFFICIAL_TIMELINE_FAILED:{official_state};FALLBACK:{fallback_count}"
        elif official_state in {"ACCESS_DENIED", "LOGIN_REQUIRED"} or "ACCESS_DENIED" in official_state or "HTTP_403" in official_state:
            truth_status=f"OFFICIAL_TIMELINE_ACCESS_DENIED:{official_state};SEARCH_FALLBACK:{fallback_count}"
        elif official_state in {"NO_POSTS_IN_72H", "NO_DATA:0"}:
            truth_status=f"OFFICIAL_TIMELINE_NO_POSTS;SEARCH_FALLBACK:{fallback_count}" if fallback_count else "OFFICIAL_TIMELINE_NO_POSTS"
        elif fallback_count:
            truth_status=f"OFFICIAL_TIMELINE_UNAVAILABLE:{official_state};SEARCH_FALLBACK:{fallback_count}"
        else:
            truth_status="NO_POSTS_IN_WINDOW"
        result=RunResult(run_id=f"TRUMP-RUN-{started.astimezone(ZoneInfo(self.config.timezone)):%Y%m%d-%H%M%S}",started_at=started,
            completed_at=datetime.now(timezone.utc),lookback_hours=self.config.lookback_hours,timezone=self.config.timezone,status=status,
            rule_version="TRUMP_RULE_V2.3.8",prompt_version="TRUMP_PROMPT_V2.3.8",model_version="V237_LIVE_EVIDENCE_CLUSTER_MATERIALITY_V2.3.8",schema_version=self.config.schema_version,
            source_status=source_status,source_counts=source_counts,source_observations=source_observations,source_priority=SOURCE_PRIORITY_LABELS,data_mode="SAMPLE" if self.config.sample_mode else "ONLINE",
            truth_social_status=truth_status,events=events,warnings=warnings,taiwan_candidates=candidates,watchlist_paths=[])
        logger.info("run complete | run_id=%s | status=%s | events=%d | material=%d | warnings=%d", result.run_id, result.status, len(events), sum(e.is_material for e in events), len(warnings))
        return result
