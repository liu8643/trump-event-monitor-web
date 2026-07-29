# Trump 72-hour Event Monitor V2.0

Deployable Streamlit platform with Truth-primary evidence, media verification, AI/rule classification, Taiwan-stock candidate mapping, review-required GTC WatchList, Excel/JSON/HTML/Word/PDF exports, 5-minute refresh/scheduled workflow, and SQLite history.

## Run
```bash
pip install -r requirements.txt
streamlit run app/streamlit_app.py
```

## Important limits
Truth full text requires licensed API or manual import. Search-index data remains snippet-only. Reuters/Bloomberg content is summarized only when legally supplied; no paywall bypass. Candidate stocks remain WATCH until live market and portfolio gates are connected.


## V2 功能到位狀態（正式修正版）
- Truth Social 全文：授權 API 或人工 JSON 匯入可取得完整原文；搜尋索引明確標示非全文。
- Reuters/Bloomberg 摘要：合法 Feed/API 文字提供摘要；未設定 LLM 時明確標示規則式摘錄，不冒充生成式 AI。
- AI 分類：規則分類可用；設定 AI_API_URL/AI_API_KEY/AI_MODEL 後啟用相容 LLM。
- 台股候選：事件產業映射，全部 WATCH，未接即時行情前不產 BUY_READY。
- GTC WatchList：分析完成後自動產生 JSON/CSV，UI 可下載，REVIEW_REQUIRED。
- 報告：Excel/Word/PDF/JSON/HTML 可一鍵下載。
- 排程：頁面開啟時可每5分鐘更新；GitHub Scheduled Monitor 每5分鐘 best-effort 執行。
- 歷史資料庫：可搜尋批次並查看事件、來源、影響與 WatchList；Community Cloud 本機 SQLite 非永久。
