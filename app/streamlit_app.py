from __future__ import annotations

import io
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from trump_monitor.collectors.sample import SampleAdapter
from trump_monitor.collectors.gnews import GNewsAdapter
from trump_monitor.collectors.newsapi import NewsApiAdapter
from trump_monitor.collectors.google_news_rss import GoogleNewsRssAdapter
from trump_monitor.collectors.cnbc import CnbcNewsAdapter
from trump_monitor.collectors.truth_social import TruthTimelineCollector, TruthOfficialApiAdapter, TruthManualImportAdapter, TruthSearchIndexAdapter
from trump_monitor.config import load_config
from trump_monitor.engine import TrumpEventEngine
from trump_monitor.exporters.excel_exporter import export_excel
from trump_monitor.exporters.json_exporter import export_json
from trump_monitor.exporters.html_exporter import export_html
from trump_monitor.repository import EventRepository
from trump_monitor.watchlist import update_watchlist
from trump_monitor.source_health import build_source_health, source_health_summary
from trump_monitor.exporters.docx_exporter import export_docx
from trump_monitor.exporters.pdf_exporter import export_pdf
from trump_monitor.logging_utils import configure_logging, build_debug_bundle
try:
    from streamlit_autorefresh import st_autorefresh
except Exception:
    st_autorefresh = None

st.set_page_config(page_title="川普72小時事件監控", page_icon="📡", layout="wide")
APP_VERSION = "2.3.8"

CONFIG_PATH = ROOT / "config.yaml"
if not CONFIG_PATH.exists():
    CONFIG_PATH = ROOT / "config.example.yaml"
config = load_config(CONFIG_PATH)
DATA_PATH = ROOT / "data" / "sample_items.json"
OUTPUT = ROOT / config.output_dir
DB_PATH = OUTPUT / "trump_events.sqlite3"
RUNTIME_TRUTH_PATH = OUTPUT / "truth_manual_posts_runtime.json"
LOGGER = configure_logging(OUTPUT)

@st.cache_resource
def repository() -> EventRepository:
    return EventRepository(DB_PATH)


def build_adapters(mode: str):
    mode = mode.upper()
    if mode == "SAMPLE":
        return [SampleAdapter(DATA_PATH)]
    # V2.2 adds the configured official public profile timeline as the highest-priority source.
    # All original adapters are retained below in their original fallback order.
    adapters = []
    if config.truth_official_timeline_enabled:
        adapters.append(TruthTimelineCollector(
            config.truth_profile_url, config.truth_account,
            account_id=config.truth_official_account_id,
            timeout=config.truth_official_timeline_timeout,
            max_pages=config.truth_official_timeline_max_pages,
            rendered_html_enabled=config.truth_rendered_html_enabled,
            static_html_enabled=config.truth_static_html_enabled,
            rendered_timeout=config.truth_rendered_timeout,
            chromium_executable=config.truth_chromium_executable,
        ))
    truth_api_url = os.getenv("TRUTH_API_BASE_URL") or config.truth_api_base_url
    if truth_api_url and os.getenv("TRUTH_API_TOKEN"):
        adapters.append(TruthOfficialApiAdapter(truth_api_url, config.truth_account))
    adapters.append(TruthManualImportAdapter(RUNTIME_TRUTH_PATH if RUNTIME_TRUTH_PATH.exists() else ROOT / config.truth_manual_import_path, config.truth_account))
    adapters.append(TruthSearchIndexAdapter(config.truth_account))
    # CNBC originally arrived indirectly inside Google News RSS. V2.2.2 gives it an explicit adapter/status while retaining the general RSS source.
    if config.cnbc_enabled:
        adapters.append(CnbcNewsAdapter(timeout=config.cnbc_timeout))
    # Verification and supplemental media follow.
    adapters.append(GoogleNewsRssAdapter())
    if os.getenv("GNEWS_API_KEY"):
        adapters.append(GNewsAdapter())
    if os.getenv("NEWSAPI_API_KEY"):
        adapters.append(NewsApiAdapter())
    return adapters


def run_analysis(mode: str):
    cfg = config.__class__(**{**config.__dict__, "mode": mode.upper()})
    engine = TrumpEventEngine(cfg, build_adapters(mode))
    with st.status("正在執行 72 小時事件分析...", expanded=True) as status:
        steps = [
            (5,"建立執行批次"),(20,"收集資料來源"),(30,"正規化時間與網址"),(40,"去重"),(52,"事件聚類"),
            (62,"事實分層"),(72,"事件評分"),(82,"市場映射"),(94,"準備輸出"),(100,"GTC Schema 驗證"),
        ]
        bar = st.progress(0)
        for pct, text in steps:
            st.write(f"{pct}% — {text}")
            bar.progress(pct)
        result = engine.run(datetime.now(timezone.utc))
        j,c=update_watchlist(result.taiwan_candidates,OUTPUT); result.watchlist_paths=[str(j),str(c)]
        repository().save_run(result)
        status.update(label=f"完成：{result.status}", state="complete" if result.status in {"SUCCESS", "PARTIAL"} else "error")
    st.session_state["result"] = result
    return result


def get_result():
    return st.session_state.get("result")

with st.sidebar:
    st.title("📡 Trump News Center")
    st.caption(f"正式版本 v{APP_VERSION}｜V2.3.5基線修正版：事件聚類、重大性Gate、分類防誤判、Debug Log可下載")
    page = st.radio("功能", [
        "首頁總覽","事件中心","事件分析","新聞明細","Truth貼文","市場影響","台股候選","GTC預覽","報表中心","歷史執行","來源設定","系統Log"
    ])
    mode = st.selectbox("資料模式", ["AUTO", "ONLINE", "SAMPLE"], index=0, help="AUTO/ONLINE 使用真實新聞來源；SAMPLE 只能手動選擇作測試。")
    if mode == "SAMPLE":
        st.warning("SAMPLE 是測試資料，不可作投資分析。")
    else:
        current_result = get_result()
        if current_result is None:
            st.info("ONLINE 已設定：優先嘗試 Truth Social Official Timeline；Reuters/AP/Bloomberg/CNBC 與聚合新聞作交叉驗證。實際是否取得第一手貼文，需以本次來源狀態為準。")
        elif current_result.source_counts.get("truth_official_timeline", 0) > 0:
            st.success(f"ONLINE：Truth Social Official Timeline 第一手貼文 {current_result.source_counts.get('truth_official_timeline',0)} 筆；CNBC {current_result.source_counts.get('cnbc',0)} 筆；其他媒體交叉驗證。")
        else:
            st.warning(f"ONLINE：本次未取得 Truth Social Official Timeline 第一手貼文；目前使用搜尋索引/媒體來源降級分析。Truth狀態：{current_result.truth_social_status}")
    auto5=st.checkbox("每5分鐘自動更新（頁面開啟時）",value=False)
    if auto5 and st_autorefresh: st_autorefresh(interval=300000,key="v2_auto_refresh")
    if st.button("開始／重新分析", type="primary", width="stretch") or (auto5 and "result" in st.session_state):
        run_analysis(mode)
    result = get_result()
    if result:
        st.caption(f"Run ID: {result.run_id}")
        st.caption(f"Status: {result.status}")

if page == "首頁總覽":
    st.title("川普 72 小時事件監控與 GTC 整合")
    if result := get_result():
        if result.data_mode == "SAMPLE":
            st.error("目前是 SAMPLE 測試資料，不可用於投資分析。")
        elif result.status in {"DATA_UNAVAILABLE", "SOURCE_FAILED"}:
            st.error("正式來源無可用資料；系統沒有自動改用 Sample。")
        else:
            st.success("目前使用最近 72 小時真實新聞來源。")
    result = get_result()
    if not result:
        st.info("請由左側按下「開始／重新分析」。")
    else:
        c1,c2,c3,c4 = st.columns(4)
        c1.metric("事件總數", len(result.events))
        c2.metric("真正重大事件", sum(e.is_material for e in result.events))
        c3.metric("警告數", len(result.warnings))
        c4.metric("來源狀態", result.status)
        if result.status in {"DATA_UNAVAILABLE", "SOURCE_FAILED"}:
            st.warning("沒有可用正式新聞，請查看來源設定與系統 Log。")

        st.subheader("來源健康儀表板")
        health_rows = build_source_health(result)
        health_summary = source_health_summary(health_rows)
        h1, h2, h3, h4, h5 = st.columns(5)
        h1.metric("成功來源", f"{health_summary['success']} / {health_summary['total']}")
        h2.metric("部分來源", health_summary["partial"])
        h3.metric("失敗來源", health_summary["failed"])
        h4.metric("無資料來源", health_summary["no_data"])
        h5.metric("未設定來源", health_summary["not_configured"])
        health_df = pd.DataFrame(health_rows)[["來源", "筆數", "狀態", "覆蓋率", "角色", "詳細狀態"]]
        st.dataframe(
            health_df,
            width="stretch",
            hide_index=True,
            column_config={
                "筆數": st.column_config.NumberColumn(format="%d"),
                "覆蓋率": st.column_config.ProgressColumn(
                    "來源覆蓋率", min_value=0, max_value=100, format="%d%%"
                ),
            },
        )
        if health_summary["failed"]:
            st.warning("部分來源失敗；請查看『詳細狀態』、來源設定或系統 Log。其他成功來源仍會繼續分析。")
        elif health_summary["no_data"]:
            st.info("部分來源在最近72小時沒有資料；這不等同於連線失敗。")

        truth_notes=[o for o in result.source_observations if o.source_key=="truth_official_timeline"]
        if truth_notes:
            with st.expander("Truth Official 四層取得紀錄／人工查閱", expanded=not bool(result.source_counts.get("truth_official_timeline",0))):
                st.link_button("開啟 Truth Social 官方帳號自行查閱", config.truth_profile_url)
                st.dataframe(pd.DataFrame([{
                    "層級":o.layer,"狀態":o.status,"畫面/回傳內容":o.displayed_text,"備註":o.note,
                    "可進事件引擎":o.eligible_for_event_engine,"證據品質":o.evidence_quality,"網址":o.url
                } for o in truth_notes]), width="stretch", hide_index=True)

        rows=[]
        for e in result.events:
            rows.append({"星等":"★"*e.score.importance,"主題":e.topic,"類別":e.category,"可信度":e.score.confidence,"GTC":e.battle_action,"最新時間":e.last_seen})
        if rows:
            df=pd.DataFrame(rows)
            st.dataframe(df, width="stretch", hide_index=True, column_config={"可信度":st.column_config.ProgressColumn(min_value=0,max_value=1,format="%.0f%%")})
            impact_rows=[]
            for e in result.events:
                for i in e.impacts: impact_rows.append({"事件":e.event_id,"資產":i.asset,"分數":i.final_score})
            chart_df=pd.DataFrame(impact_rows).pivot_table(index="資產",columns="事件",values="分數",aggfunc="mean").fillna(0)
            st.bar_chart(chart_df)

elif page == "事件中心":
    st.header("事件中心")
    result=get_result()
    if not result: st.info("尚無分析結果。")
    else:
        options={f"{'★'*e.score.importance} {e.topic}":e for e in result.events}
        selected=st.selectbox("選擇事件", list(options))
        e=options[selected]
        c1,c2=st.columns([1,2])
        with c1:
            st.metric("可信度",f"{e.score.confidence:.0%}")
            st.metric("Rule Score",e.score.rule_score)
            st.metric("GTC",e.battle_action)
            st.json(e.score.breakdown)
        with c2:
            st.subheader(e.topic); st.write(e.summary)
            st.caption(f"Event ID: {e.event_id}｜{e.first_seen} → {e.last_seen}")
            st.write("受惠：", "、".join(e.beneficiary_sectors) or "無")
            st.write("受壓：", "、".join(e.negative_sectors) or "無")

elif page == "事件分析":
    st.header("事件分析")
    result=get_result()
    if not result: st.info("尚無分析結果。")
    else:
        for e in result.events:
            with st.expander(f"{'★'*e.score.importance} {e.topic}"):
                st.json(e.score.model_dump())
                st.dataframe(pd.DataFrame([i.model_dump() for i in e.impacts]),width="stretch",hide_index=True)
                st.info("人工覆核功能於正式資料庫版本可寫入 manual_reviews；本 MVP 保留介面規格，不修改附件中的既有 GTC 作戰等級。")

elif page == "新聞明細":
    st.header("新聞明細與證據鏈")
    result=get_result()
    if not result: st.info("尚無分析結果。")
    else:
        rows=[]
        for e in result.events:
            for s in e.sources:
                rows.append({"發布時間":s.published_at,"事件ID":e.event_id,"標題":s.title,"摘要":s.ai_summary_zh,"摘要方式":s.ai_summary_status,"分析器":s.ai_provider,"AI情緒":s.ai_sentiment,"內容狀態":s.content_status,"來源":s.source_name,"Publisher Group":s.publisher_group,"來源角色":s.source_type,"直接引用":s.direct_quote,"URL":s.url})
        st.dataframe(pd.DataFrame(rows),width="stretch",hide_index=True,column_config={"URL":st.column_config.LinkColumn()})

elif page == "Truth貼文":
    st.header("Truth Social 第一手貼文")
    st.caption("完整全文僅在授權 API 或人工匯入取得；搜尋索引只會標示為摘要/片段，不冒充全文。")
    uploaded=st.file_uploader("匯入 Truth Social 原始貼文 JSON（可選）",type=["json"],help="JSON陣列欄位：published_at、body/text、url，可選title/raw_item_id。")
    if uploaded is not None:
        try:
            import json
            rows=json.loads(uploaded.getvalue().decode("utf-8-sig"))
            if not isinstance(rows,list): raise ValueError("最外層必須是JSON陣列")
            OUTPUT.mkdir(parents=True,exist_ok=True); RUNTIME_TRUTH_PATH.write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding="utf-8")
            st.success(f"已匯入 {len(rows)} 筆；請按左側『開始／重新分析』。")
        except Exception as exc: st.error(f"匯入失敗：{exc}")
    result=get_result()
    posts=[] if not result else [(e,s) for e in result.events for s in e.sources if s.source_type=="DIRECT_POST"]
    if not posts: st.warning(f"最近72小時未取得Truth Social第一手貼文。狀態：{result.truth_social_status if result else '尚未分析'}。不以Sample替代。")
    for e,s in posts:
        with st.container(border=True):
            st.subheader(s.title)
            if s.content_status=="FULL_OR_LICENSED": st.success("內容狀態：完整/授權原文")
            else: st.warning(f"內容狀態：{s.content_status}（不是完整原文）")
            st.write(s.body or "未取得文字內容")
            st.info(f"摘要：{s.ai_summary_zh}｜摘要方式：{s.ai_summary_status}｜分析器：{s.ai_provider}｜情緒：{s.ai_sentiment}")
            if s.url: st.link_button("開啟原始貼文",s.url)
            st.caption(f"{e.event_id}｜取得方式：{s.acquisition_method}")

elif page == "市場影響":
    st.header("市場影響")
    result=get_result()
    if not result: st.info("尚無分析結果。")
    else:
        rows=[{"事件ID":e.event_id,"資產":i.asset,"Rule":i.rule_score,"AI":i.ai_score,"綜合分數":i.final_score,"信心度":i.confidence,"方向":i.direction,"理由":i.rationale,"期間":i.horizon} for e in result.events for i in e.impacts]
        st.dataframe(pd.DataFrame(rows),width="stretch",hide_index=True)

elif page == "台股候選":
    st.header("台股候選（風險 Gate）")
    result=get_result()
    if not result: st.info("尚無分析結果。")
    else:
        rows=result.taiwan_candidates
        st.dataframe(pd.DataFrame(rows),width="stretch",hide_index=True)
        st.warning("V2以事件/產業映射產生候選與內部WatchList；未接即時價格、流動性與持倉前，一律WATCH，不直接BUY_READY。")

elif page == "GTC預覽":
    st.header("GTC 預覽")
    result=get_result()
    if not result: st.info("尚無分析結果。")
    else:
        st.success(f"Schema: {result.schema_version}")
        tabs=st.tabs(["今日策略","控制欄","宏觀16","三大劇本","每日追蹤"])
        top=result.events[:3]
        with tabs[0]:
            for e in top: st.write(f"{'★'*e.score.importance}｜{e.category}｜{e.battle_action}｜{e.topic}")
        with tabs[1]: st.info("外部事件提示，不覆蓋既有盤中動態作戰等級。")
        with tabs[2]: st.write([{"event_id":e.event_id,"summary":e.summary} for e in top])
        with tabs[3]: st.write("Risk-Off" if any(e.battle_action=="REDUCE" for e in top) else "Neutral")
        with tabs[4]: st.dataframe(pd.DataFrame([{"event_id":e.event_id,"score":e.score.final_score,"action":e.battle_action} for e in result.events]),hide_index=True)

elif page == "報表中心":
    st.header("報表中心")
    result=get_result()
    if not result: st.info("尚無分析結果。")
    else:
        OUTPUT.mkdir(parents=True,exist_ok=True)
        xlsx=export_excel(result,OUTPUT/f"川普72小時事件報告_{result.run_id}.xlsx")
        js=export_json(result,OUTPUT/f"trump_events_{result.run_id}.json")
        html=export_html(result,OUTPUT/f"trump_report_{result.run_id}.html")
        docx=export_docx(result,OUTPUT/f"trump_report_{result.run_id}.docx")
        pdf=export_pdf(result,OUTPUT/f"trump_report_{result.run_id}.pdf")
        c1,c2,c3=st.columns(3)
        c1.download_button("下載 Excel",xlsx.read_bytes(),xlsx.name,"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",width="stretch")
        c2.download_button("下載 Word",docx.read_bytes(),docx.name,"application/vnd.openxmlformats-officedocument.wordprocessingml.document",width="stretch")
        c3.download_button("下載 PDF",pdf.read_bytes(),pdf.name,"application/pdf",width="stretch")
        c4,c5,c6=st.columns(3)
        c4.download_button("下載 JSON",js.read_bytes(),js.name,"application/json",width="stretch")
        c5.download_button("下載 HTML",html.read_bytes(),html.name,"text/html",width="stretch")
        watch_paths=[Path(x) for x in result.watchlist_paths if Path(x).exists()]
        if len(watch_paths)>=2:
            c6.download_button("下載 GTC WatchList JSON",watch_paths[0].read_bytes(),watch_paths[0].name,"application/json",width="stretch")
            st.download_button("下載 GTC WatchList CSV",watch_paths[1].read_bytes(),watch_paths[1].name,"text/csv",width="stretch")
        debug_zip=build_debug_bundle(OUTPUT,result.run_id)
        st.download_button("下載 Debug Log ZIP",debug_zip.read_bytes(),debug_zip.name,"application/zip",width="stretch")
        st.caption("GTC WatchList 為 REVIEW_REQUIRED；不會未經確認直接改寫既有 GTC 資料庫。")

elif page == "歷史執行":
    st.header("歷史事件資料庫（查詢與回溯）")
    runs=repository().list_runs(100)
    if not runs: st.info("尚無歷史執行。")
    else:
        q=st.text_input("搜尋 Run ID／日期／狀態")
        filtered=[r for r in runs if not q or q.lower() in " ".join(str(v) for v in r.values()).lower()]
        st.dataframe(pd.DataFrame(filtered),width="stretch",hide_index=True)
        ids=[r["run_id"] for r in filtered]
        if ids:
            selected=st.selectbox("選擇批次查看明細",ids)
            tabs=st.tabs(["事件","來源","市場影響","WatchList","完整JSON"])
            with tabs[0]: st.dataframe(pd.DataFrame(repository().list_events(selected)),width="stretch",hide_index=True)
            with tabs[1]: st.dataframe(pd.DataFrame(repository().list_sources(selected)),width="stretch",hide_index=True)
            with tabs[2]: st.dataframe(pd.DataFrame(repository().list_impacts(selected)),width="stretch",hide_index=True)
            with tabs[3]: st.dataframe(pd.DataFrame(repository().list_watchlist(selected)),width="stretch",hide_index=True)
            with tabs[4]:
                old_run=repository().load_run(selected)
                st.json(old_run.model_dump(mode="json") if old_run else {})
        st.warning("Streamlit Community Cloud 本機 SQLite 可能在重啟後消失；長期永久保存需外接 PostgreSQL/Supabase/S3。")

elif page == "來源設定":
    st.header("來源設定與健康")
    st.subheader("正式資料來源優先順序")
    st.markdown(f"1. **Truth Social Official Timeline**：[{config.truth_account}]({config.truth_profile_url}) 公開時間軸 → 時間排序 → 72小時篩選\n2. **原有Truth來源保留**：授權API → 人工匯入 → 搜尋索引發現\n3. **Reuters／AP／Bloomberg**：交叉驗證\n4. **Google News RSS**：補充\n5. **NewsAPI／GNews**：補充")
    st.write({"Truth Social Official URL":config.truth_profile_url,"Truth Official Timeline啟用":config.truth_official_timeline_enabled,"Truth API Token":bool(os.getenv("TRUTH_API_TOKEN")),"Truth API Endpoint":bool(os.getenv("TRUTH_API_BASE_URL") or config.truth_api_base_url),"Truth人工匯入":str(ROOT/config.truth_manual_import_path),"CNBC來源啟用":config.cnbc_enabled,"Google News RSS":True,"GNews Key":bool(os.getenv("GNEWS_API_KEY")),"NewsAPI Key":bool(os.getenv("NEWSAPI_API_KEY"))})
    if result := get_result():
        health_rows = build_source_health(result)
        st.dataframe(
            pd.DataFrame(health_rows)[["來源", "筆數", "狀態", "覆蓋率", "角色", "詳細狀態"]],
            width="stretch",
            hide_index=True,
            column_config={"覆蓋率": st.column_config.ProgressColumn("來源覆蓋率", min_value=0, max_value=100, format="%d%%")},
        )
        with st.expander("原始來源狀態（工程用）"):
            st.write("來源狀態", result.source_status)
            if result.source_observations:
                st.write("來源觀察紀錄（含Static HTML／人工查閱備註）", [o.model_dump(mode="json") for o in result.source_observations])
            st.write("來源筆數", result.source_counts)
            st.write("Truth Social 狀態", result.truth_social_status)
    st.info("正式來源失敗時會明確顯示FAILED／RATE_LIMIT／LOGIN_REQUIRED等原因，不會以Sample替代。")

elif page == "系統Log":
    st.header("系統 Log / Debug Evidence")
    result=get_result()
    if not result: st.info("尚無分析結果；runtime/debug/error log 仍會保存在 output/logs。")
    else:
        st.json({"run_id":result.run_id,"status":result.status,"data_mode":result.data_mode,"truth_social_status":result.truth_social_status,"source_status":result.source_status,"warnings":result.warnings,"versions":{"rule":result.rule_version,"prompt":result.prompt_version,"model":result.model_version,"schema":result.schema_version}})
    log_dir=OUTPUT/"logs"
    for filename in ["runtime.log","debug.log","error.log"]:
        path=log_dir/filename
        if path.exists():
            st.download_button(f"下載 {filename}",path.read_bytes(),filename,"text/plain",width="stretch")
    bundle=build_debug_bundle(OUTPUT,result.run_id if result else "")
    st.download_button("下載完整 Debug Log ZIP",bundle.read_bytes(),bundle.name,"application/zip",width="stretch")
