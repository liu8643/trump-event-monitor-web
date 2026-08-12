
## V2.3 首頁來源健康儀表板

首頁會固定列出 Truth Official、Truth Search、Reuters、AP、Bloomberg、CNBC、Google RSS、NewsAPI 與 GNews，並顯示每個來源的最近72小時筆數、SUCCESS／NO_DATA／FAILED／NOT_CONFIGURED、覆蓋率與詳細狀態。Reuters/AP/Bloomberg 的筆數由事件證據中的 publisher_group 去重統計；CNBC 為獨立 CnbcNewsAdapter 狀態。


## V2.2 Truth Social Official Timeline

V2.2 在不移除任何既有來源或功能的前提下，新增最高優先來源：
`https://truthsocial.com/@realDonaldTrump?gsid=9b589f48-461b-4500-b6f3-2a1e34d7e317`。
系統由同一 Truth Social 網域的公開 JSON 時間軸介面解析 `@realDonaldTrump`，明確依時間排序並套用 72 小時篩選；原授權 API、人工匯入、搜尋索引與新聞來源全部保留。若公開時間軸介面回傳 401/403/429、非 JSON 或結構變更，來源狀態會明確失敗並繼續使用原有來源，不會用 Sample 偽裝正式資料。
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

## V2.2.2 CNBC來源說明
原CNBC新聞並非獨立Collector，而是由Google News RSS的Publisher欄位間接取得。V2.2.2新增`CnbcNewsAdapter`，仍使用無金鑰Google News RSS，但將CNBC限定查詢、執行狀態與筆數獨立化；一般Google News RSS及所有原來源均保留，重複資料由既有去重流程處理。

## V2.3.7（基於 V2.3.5）工程修正

- 正式主引擎啟用 `clustering.py`，事件依語意聚類，不再把整個分類桶誤當同一事件。
- 新增 0–100 `materiality_score` 與 BLACK/RED/ORANGE/YELLOW/WATCH 等級；`is_material` 門檻預設 65。
- 新增「總統安全／國安」與「醫療／社會政策」分類護欄，避免 Secret Flight 類事件跨類別拆分，以及 Medicaid `CHIP` 被誤判成半導體 chip。
- `Truth Social` 僅在 TMTG/DJT 公司/平台業務語意時分類為社群/TMTG；一般第一手貼文按事件內容分類。
- AP News / Associated Press publisher alias 納入來源健康統計。
- `output/logs/` 保存 `runtime.log`、`debug.log`、`error.log`，Streamlit「系統Log」及「報表中心」均可下載 Debug Log ZIP。
- SAMPLE 測試固定評估時間，避免固定樣本因執行日期漂移導致 72 小時窗假失敗。
