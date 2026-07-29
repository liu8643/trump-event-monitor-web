from __future__ import annotations
from datetime import datetime,timedelta,timezone
from zoneinfo import ZoneInfo
from trump_monitor.classifier import classify_category,classify_source_type
from trump_monitor.config import AppConfig
from trump_monitor.dedup import deduplicate
from trump_monitor.impact import build_impacts
from trump_monitor.models import EventCluster,RunResult
from trump_monitor.scoring import score_event
from trump_monitor.collectors.source_policy import SOURCE_PRIORITY_LABELS
from trump_monitor.ai_service import analyze
from trump_monitor.taiwan_stocks import rank_candidates
from trump_monitor.clustering import cluster_items

class TrumpEventEngine:
    def __init__(self,config:AppConfig,adapters:list): self.config,self.adapters=config,adapters

    def run(self,now:datetime|None=None)->RunResult:
        started=now or datetime.now(timezone.utc)
        if started.tzinfo is None: started=started.replace(tzinfo=timezone.utc)
        start=started-timedelta(hours=self.config.lookback_hours)
        raw=[]; source_status={}; source_counts={}; warnings=[]
        for adapter in self.adapters:
            try:
                rows=adapter.collect(start,started); raw.extend(rows)
                source_counts[adapter.name]=len(rows); source_status[adapter.name]=f"SUCCESS:{len(rows)}"
            except Exception as exc:
                source_counts[adapter.name]=0; source_status[adapter.name]=f"FAILED:{type(exc).__name__}:{str(exc)[:240]}"; warnings.append(f"{adapter.name}: {exc}")
        unique,_=deduplicate(raw); categories={}
        for item in unique:
            item.source_type=classify_source_type(item)  # type: ignore[misc]
            ai=analyze(item.title,item.body)
            item.ai_summary_zh=ai.summary_zh; item.ai_sentiment=ai.sentiment; item.ai_provider=ai.provider; item.ai_summary_status=ai.summary_status
            if item.acquisition_method in {"LICENSED_API","MANUAL_IMPORT"} and item.body: item.content_status="FULL_OR_LICENSED"
            elif item.body: item.content_status="SNIPPET_OR_FEED_SUMMARY"
            categories[item.raw_item_id]=ai.category or classify_category(item)
        grouped=cluster_items(unique,categories)
        events=[]
        for idx,(category,items) in enumerate(grouped,1):
            score=score_event(items,category); impacts=build_impacts(category,score,items)
            ordered=sorted(items,key=lambda x:(x.source_tier,-x.source_confidence,-x.published_at.timestamp()))
            top=ordered[0]; event_id=f"TRUMP-{started.astimezone(ZoneInfo(self.config.timezone)):%Y%m%d}-{idx:03d}"
            beneficiary=sorted({x for i in impacts for x in i.beneficiary.split("、") if x}); negative=sorted({x for i in impacts for x in i.negative.split("、") if x})
            verified=len({x.publisher_group for x in items if x.source_tier==2})
            primary=any(x.source_type in {"DIRECT_POST","OFFICIAL_POLICY"} for x in items)
            quality="HIGH" if primary and verified>=1 else "MEDIUM" if verified>=1 or len({x.publisher_group for x in items})>=2 else "LIMITED"
            gate="REVIEW_REQUIRED" if score.confidence>=.8 and abs(score.final_score)>=3 else "WATCH_ONLY"
            action="REDUCE" if any(i.asset=="台股" and i.final_score<=-2 for i in impacts) and score.confidence>=.75 else "WATCH"
            summary=top.ai_summary_zh or (top.body or top.title)[:500]
            timeline=[{"time":x.published_at.isoformat(),"source":x.source_name,"role":x.source_role,"headline":x.title} for x in sorted(items,key=lambda x:x.published_at)]
            facts=[x.ai_summary_zh or x.title for x in ordered[:3]]
            rationale=f"證據品質{quality}；{len(items)}筆來源、{verified}個驗證媒體；台股事件分數{next((i.final_score for i in impacts if i.asset=='台股'),0)}；Gate={gate}。"
            events.append(EventCluster(event_id=event_id,topic=top.title,category=category,summary=summary,first_seen=min(x.published_at for x in items),last_seen=max(x.published_at for x in items),source_count=len({x.publisher_group for x in items}),sources=ordered,score=score,impacts=impacts,beneficiary_sectors=beneficiary,negative_sectors=negative,battle_action=action,event_label=category.replace("／","_").replace(" ","_").upper(),data_freshness="SAMPLE" if self.config.sample_mode else "CURRENT",primary_source_present=primary,verification_source_count=verified,key_facts=facts,timeline=timeline,evidence_quality=quality,contradiction_count=0,decision_rationale=rationale,gtc_gate=gate))
        events.sort(key=lambda e:(e.score.importance,e.evidence_quality=="HIGH",e.verification_source_count,e.score.confidence,e.last_seen),reverse=True)
        candidates=rank_candidates(events)
        for e in events: e.taiwan_candidates=[x for x in candidates if e.event_id in x.get("reasons","")][:10]
        status="SUCCESS" if events and not warnings else "PARTIAL" if events else ("SOURCE_FAILED" if warnings else "DATA_UNAVAILABLE")
        truth_sources={k:v for k,v in source_status.items() if k.startswith("truth_")}; direct_truth=sum(source_counts.get(k,0) for k in truth_sources if k in {"truth_official_api","truth_manual_import"}); discovery=source_counts.get("truth_search_index",0)
        truth_status=f"DIRECT:{direct_truth};DISCOVERY:{discovery}" if direct_truth or discovery else ("FAILED_OR_NOT_CONFIGURED" if any(v.startswith("FAILED") for v in truth_sources.values()) else "NO_POSTS_IN_WINDOW")
        return RunResult(run_id=f"TRUMP-RUN-{started.astimezone(ZoneInfo(self.config.timezone)):%Y%m%d-%H%M%S}",started_at=started,completed_at=datetime.now(timezone.utc),lookback_hours=self.config.lookback_hours,timezone=self.config.timezone,status=status,rule_version="TRUMP_RULE_V2.1",prompt_version="TRUMP_PROMPT_V2.1",model_version="EVIDENCE_EVENT_DECISION_V2.1",schema_version="gtc.trump_event.v2.1",source_status=source_status,source_counts=source_counts,source_priority=SOURCE_PRIORITY_LABELS,data_mode="SAMPLE" if self.config.sample_mode else "ONLINE",truth_social_status=truth_status,events=events,warnings=warnings,taiwan_candidates=candidates,watchlist_paths=[])
