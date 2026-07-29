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
from trump_monitor.collectors.truth_social import TruthOfficialApiAdapter, TruthManualImportAdapter, TruthSearchIndexAdapter
from trump_monitor.config import load_config
from trump_monitor.engine import TrumpEventEngine
from trump_monitor.exporters.excel_exporter import export_excel
from trump_monitor.exporters.json_exporter import export_json
from trump_monitor.exporters.html_exporter import export_html
from trump_monitor.repository import EventRepository

st.set_page_config(page_title="川普72小時事件監控", page_icon="📡", layout="wide")

CONFIG_PATH = ROOT / "config.yaml"
if not CONFIG_PATH.exists():
    CONFIG_PATH = ROOT / "config.example.yaml"
config = load_config(CONFIG_PATH)
DATA_PATH = ROOT / "data" / "sample_items.json"
OUTPUT = ROOT / config.output_dir
DB_PATH = OUTPUT / "trump_events.sqlite3"

@st.cache_resource
def repository() -> EventRepository:
    return EventRepository(DB_PATH)


def build_adapters(mode: str):
    mode = mode.upper()
    if mode == "SAMPLE":
        return [SampleAdapter(DATA_PATH)]
    # Formal priority: Truth Social first-party sources first.
    adapters = []
    truth_api_url = os.getenv("TRUTH_API_BASE_URL") or config.truth_api_base_url
    if truth_api_url and os.getenv("TRUTH_API_TOKEN"):
        adapters.append(TruthOfficialApiAdapter(truth_api_url, config.truth_account))
    adapters.append(TruthManualImportAdapter(ROOT / config.truth_manual_import_path, config.truth_account))
    adapters.append(TruthSearchIndexAdapter(config.truth_account))
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
        repository().save_run(result)
        status.update(label=f"完成：{result.status}", state="complete" if result.status in {"SUCCESS", "PARTIAL"} else "error")
    st.session_state["result"] = result
    return result


def get_result():
    return st.session_state.get("result")

with st.sidebar:
    st.title("📡 Trump News Center")
    page = st.radio("功能", [
        "首頁總覽","事件中心","事件分析","新聞明細","Truth貼文","市場影響","台股候選","GTC預覽","報表中心","歷史執行","來源設定","系統Log"
    ])
    mode = st.selectbox("資料模式", ["AUTO", "ONLINE", "SAMPLE"], index=0, help="AUTO/ONLINE 使用真實新聞來源；SAMPLE 只能手動選擇作測試。")
    if mode == "SAMPLE":
        st.warning("SAMPLE 是測試資料，不可作投資分析。")
    else:
        st.success("ONLINE：Truth Social 為第一手來源；Reuters/AP/Bloomberg 交叉驗證；Google RSS、NewsAPI、GNews補充。")
    if st.button("開始／重新分析", type="primary", use_container_width=True):
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
                rows.append({"發布時間":s.published_at,"事件ID":e.event_id,"標題":s.title,"來源":s.source_name,"Publisher Group":s.publisher_group,"來源角色":s.source_type,"直接引用":s.direct_quote,"URL":s.url})
        st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True,column_config={"URL":st.column_config.LinkColumn()})

elif page == "Truth貼文":
    st.header("Truth 貼文明細")
    result=get_result()
    posts=[] if not result else [(e,s) for e in result.events for s in e.sources if s.source_type=="DIRECT_POST"]
    if not posts: st.warning(f"最近72小時未取得Truth Social第一手貼文。狀態：{result.truth_social_status if result else '尚未分析'}。不以Sample替代。")
    for e,s in posts:
        st.subheader(s.title); st.write(s.body); st.link_button("開啟原始貼文",s.url); st.caption(e.event_id)

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
        rows=[]
        for e in result.events:
            for sec in e.beneficiary_sectors:
                rows.append({"事件ID":e.event_id,"產業":sec,"方向":"受惠候選","可信度":e.score.confidence,"資料新鮮度":e.data_freshness,"Gate":"BLOCKED_NO_MARKET_DATA" if result.data_mode == "ONLINE" else "BLOCKED_SAMPLE","GTC":"WATCH"})
        st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)
        st.warning("未接入即時台股行情、流動性與個股資料前，不產生 BUY_READY 或個股 Top10。")

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
        st.download_button("下載 Excel",xlsx.read_bytes(),xlsx.name,"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",use_container_width=True)
        st.download_button("下載 JSON",js.read_bytes(),js.name,"application/json",use_container_width=True)
        st.download_button("下載 HTML",html.read_bytes(),html.name,"text/html",use_container_width=True)

elif page == "歷史執行":
    st.header("歷史執行")
    st.dataframe(pd.DataFrame(repository().list_runs()),use_container_width=True,hide_index=True)

elif page == "來源設定":
    st.header("來源設定與健康")
    st.subheader("正式資料來源優先順序")
    st.markdown("1. **Truth Social 第一手來源**：授權API → 人工匯入 → 搜尋索引發現\n2. **Reuters／AP／Bloomberg**：交叉驗證\n3. **Google News RSS**：補充\n4. **NewsAPI／GNews**：補充")
    st.write({"Truth API Token":bool(os.getenv("TRUTH_API_TOKEN")),"Truth API Endpoint":bool(os.getenv("TRUTH_API_BASE_URL") or config.truth_api_base_url),"Truth人工匯入":str(ROOT/config.truth_manual_import_path),"Google News RSS":True,"GNews Key":bool(os.getenv("GNEWS_API_KEY")),"NewsAPI Key":bool(os.getenv("NEWSAPI_API_KEY"))})
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
