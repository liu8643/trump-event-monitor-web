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
from trump_monitor.exporters.docx_exporter import export_docx
from trump_monitor.exporters.pdf_exporter import export_pdf
try:
    from streamlit_autorefresh import st_autorefresh
except Exception:
    st_autorefresh = None

st.set_page_config(page_title="川普72小時事件監控", page_icon="📡", layout="wide")
APP_VERSION = "2.2.2"

CONFIG_PATH = ROOT / "config.yaml"
if not CONFIG_PATH.exists():
    CONFIG_PATH = ROOT / "config.example.yaml"
config = load_config(CONFIG_PATH)
DATA_PATH = ROOT / "data" / "sample_items.json"
OUTPUT = ROOT / config.output_dir
DB_PATH = OUTPUT / "trump_events.sqlite3"
RUNTIME_TRUTH_PATH = OUTPUT / "truth_manual_posts_runtime.json"

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
            timeout=config.truth_official_timeline_timeout,
            max_pages=config.truth_official_timeline_max_pages,
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
    st.caption(f"正式版本 v{APP_VERSION}｜新增 Truth Social Official Timeline；原有來源與功能保留")
    page = st.radio("功能", [
        "首頁總覽","事件中心","事件分析","新聞明細","Truth貼文","市場影響","台股候選","GTC預覽","報表中心","歷史執行","來源設定","系統Log"
    ])
    mode = st.selectbox("資料模式", ["AUTO", "ONLINE", "SAMPLE"], index=0, help="AUTO/ONLINE 使用真實新聞來源；SAMPLE 只能手動選擇作測試。")
    if mode == "SAMPLE":
        st.warning("SAMPLE 是測試資料，不可作投資分析。")
    else:
        st.success("ONLINE：Truth Social 為第一手來源；Reuters/AP/Bloomberg/CNBC 交叉驗證；Google RSS、NewsAPI、GNews補充。")
    auto5=st.checkbox("每5分鐘自動更新（頁面開啟時）",value=False)
    if auto5 and st_autorefresh: st_autorefresh(interval=300000,key="v2_auto_refresh")
    if st.button("開始／重新分析", type="primary", use_container_width=True) or (auto5 and "result" in st.session_state):
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
        c1.metric("事件數", len(result.events))
        c2.metric("高影響事件", sum(e.score.importance >= 4 for e in result.events))
        c3.metric("警告數", len(result.warnings))
        c4.metric("來源狀態", result.status)
        if result.status in {"DATA_UNAVAILABLE", "SOURCE_FAILED"}:
            st.warning("沒有可用正式新聞，請查看來源設定與系統 Log。")
        rows=[]
        for e in result.events:
            rows.append({"星等":"★"*e.score.importance,"主題":e.topic,"類別":e.category,"可信度":e.score.confidence,"GTC":e.battle_action,"最新時間":e.last_seen})
        if rows:
            df=pd.DataFrame(rows)
            st.dataframe(df, use_container_width=True, hide_index=True, column_config={"可信度":st.column_config.ProgressColumn(min_value=0,max_value=1,format="%.0f%%")})
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
                st.dataframe(pd.DataFrame([i.model_dump() for i in e.impacts]),use_container_width=True,hide_index=True)
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
        st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True,column_config={"URL":st.column_config.LinkColumn()})

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
        st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)

elif page == "台股候選":
    st.header("台股候選（風險 Gate）")
    result=get_result()
    if not result: st.info("尚無分析結果。")
    else:
        rows=result.taiwan_candidates
        st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)
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
        c1.download_button("下載 Excel",xlsx.read_bytes(),xlsx.name,"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",use_container_width=True)
        c2.download_button("下載 Word",docx.read_bytes(),docx.name,"application/vnd.openxmlformats-officedocument.wordprocessingml.document",use_container_width=True)
        c3.download_button("下載 PDF",pdf.read_bytes(),pdf.name,"application/pdf",use_container_width=True)
        c4,c5,c6=st.columns(3)
        c4.download_button("下載 JSON",js.read_bytes(),js.name,"application/json",use_container_width=True)
        c5.download_button("下載 HTML",html.read_bytes(),html.name,"text/html",use_container_width=True)
        watch_paths=[Path(x) for x in result.watchlist_paths if Path(x).exists()]
        if len(watch_paths)>=2:
            c6.download_button("下載 GTC WatchList JSON",watch_paths[0].read_bytes(),watch_paths[0].name,"application/json",use_container_width=True)
            st.download_button("下載 GTC WatchList CSV",watch_paths[1].read_bytes(),watch_paths[1].name,"text/csv",use_container_width=True)
        st.caption("GTC WatchList 為 REVIEW_REQUIRED；不會未經確認直接改寫既有 GTC 資料庫。")

elif page == "歷史執行":
    st.header("歷史事件資料庫（查詢與回溯）")
    runs=repository().list_runs(100)
    if not runs: st.info("尚無歷史執行。")
    else:
        q=st.text_input("搜尋 Run ID／日期／狀態")
        filtered=[r for r in runs if not q or q.lower() in " ".join(str(v) for v in r.values()).lower()]
        st.dataframe(pd.DataFrame(filtered),use_container_width=True,hide_index=True)
        ids=[r["run_id"] for r in filtered]
        if ids:
            selected=st.selectbox("選擇批次查看明細",ids)
            tabs=st.tabs(["事件","來源","市場影響","WatchList","完整JSON"])
            with tabs[0]: st.dataframe(pd.DataFrame(repository().list_events(selected)),use_container_width=True,hide_index=True)
            with tabs[1]: st.dataframe(pd.DataFrame(repository().list_sources(selected)),use_container_width=True,hide_index=True)
            with tabs[2]: st.dataframe(pd.DataFrame(repository().list_impacts(selected)),use_container_width=True,hide_index=True)
            with tabs[3]: st.dataframe(pd.DataFrame(repository().list_watchlist(selected)),use_container_width=True,hide_index=True)
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
        st.write("來源狀態", result.source_status)
        st.write("來源筆數", result.source_counts)
        st.write("Truth Social 狀態", result.truth_social_status)
    st.info("正式來源失敗時會明確顯示FAILED／RATE_LIMIT／LOGIN_REQUIRED等原因，不會以Sample替代。")

elif page == "系統Log":
    st.header("系統 Log")
    result=get_result()
    if not result: st.info("尚無分析結果。")
    else:
        st.json({"run_id":result.run_id,"status":result.status,"data_mode":result.data_mode,"truth_social_status":result.truth_social_status,"source_status":result.source_status,"warnings":result.warnings,"versions":{"rule":result.rule_version,"prompt":result.prompt_version,"model":result.model_version,"schema":result.schema_version}})
