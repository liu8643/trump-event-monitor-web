
## V2.3.17 — 2026-08-25 14:01 Live root-cause fix
- 14:01 Production Run showed 108/108 network translations failed even after Google→MyMemory→Lingva. Adds `LOCAL_RULE_ZH_TW` as a deterministic offline Traditional-Chinese reading layer so the Chinese column no longer collapses to blank when all public providers are throttled. It is explicitly labeled `SUCCESS:LOCAL_RULE_PARTIAL`; English remains authoritative evidence.
- Translation reporting now distinguishes full/network translation from `LOCAL_PARTIAL` quality instead of treating every nonblank Chinese string as equivalent.
- GDELT ReadTimeout/transport failures now open the persisted degraded-source circuit and return cache/degraded state instead of throwing `SourceError` traceback on every run.
- Retains V2.3.16 Federal Register, U.S. Treasury, lightweight Truth Rendered disablement, clustering and Materiality fixes.
## V2.3.15 11:51 Live Evidence 修正版

本版直接依 `TRUMP-RUN-20260825-115155` 的 Live Excel + UI CSV + Debug ZIP 進行三輪交互分析。V2.3.14 已證明翻譯 Circuit Fallback 成功：103/103 標題由 `MYMEMORY_PUBLIC` 取得繁中，翻譯耗時約 29.4 秒；本版保留該能力並新增台灣用語正規化（`特朗普` → `川普`）。新發現的主要瓶頸是 GDELT：公開端點仍回 HTTP 429，單一 Adapter 讓 Live Run 額外耗時約 52 秒。因此 V2.3.15 將公開 rate limit 視為可預期的 degraded state，預設單次嘗試後開啟持久化 30 分鐘 Circuit，後續 Run 直接使用時間窗內 Cache 或快速標示 `DEGRADED:CIRCUIT_OPEN_NO_CACHE`，不再每五分鐘重複產生 Error traceback 與長時間等待。

11:51 報告也證實同一個「加拿大 50% 汽車關稅」政策行動仍被拆成多個事件群（CNBC/BBC/PBS、Reuters、Washington Post/Guardian/Politico）。本版新增窄事件家族 `CANADA_50_AUTO_TARIFF_ACTION`，避免同一政策公告重複計算。Materiality 同步增加正式制裁行動與最高法院選舉制度裁決的語意嚴重度，並修正 context penalty：單一 Opinion 不得拖低整個多來源正式政策事件。

另修正分類融合：當 Rule/LLM 只回 `其他／一般政治`，但 deterministic classifier 已辨識出更精確類別（例如 Hormuz → 地緣政治／能源），不得再被 generic AI 結果覆蓋。09_來源健康新增每個 Adapter 的實際耗時秒數，讓 GDELT/Truth 等慢來源可直接從報表判讀，不必只靠 Debug Log。

## V2.3.14 GitHub CI Test-Isolation 修正版

本版針對 GitHub Actions #60 的真實 CI 失敗（Python 3.11：62 passed / 2 failed）修正測試污染。V2.3.13 的翻譯 Circuit Breaker 是正確的 process-level production state，但舊 V2.3.11/V2.3.12 regression tests 未隔離 `_GOOGLE_BLOCKED_UNTIL` / `_MYMEMORY_BLOCKED_UNTIL` 等 volatile state，造成測試結果依賴執行順序：兩個失敗測試單獨執行皆 PASS，全套執行才 FAIL。V2.3.14 新增 autouse test fixture，在每個 pytest case 前後重置翻譯 runtime state，CI 預設禁止真實外網翻譯，翻譯專測則明確啟用並 mock HTTP；CI matrix 同時保留 3.11 與 3.14，並設定 fail-fast:false，確保兩個版本都跑完。Production 翻譯 Circuit Breaker / MyMemory fallback / GDELT / Materiality 邏輯不回退。

## V2.3.13 11:04 Live Run 三輪交互分析修正版

本版直接由 TRUMP-RUN-20260825-110400 的 Excel、UI CSV、Debug ZIP 與 Streamlit Cloud Log 反查。V2.3.12 已成功修正重大性誤判、市場/產業聚合與Runtime翻譯KPI；但正式Run仍顯示 103/103 headline translation失敗，且翻譯階段耗時約6分11秒；GDELT則出現HTTP 200但內容非JSON。V2.3.13因此加入Google 429 Circuit Breaker + MyMemory public fallback、GDELT soft-rate-limit/non-JSON處理與cache降級，並新增移民／邊境政策分類。Public翻譯服務仍屬best-effort；正式企業環境仍建議設定AI_API_URL/API_KEY/MODEL。

## V2.3.12 09:34 Live Run 三輪交互分析修正版

本版直接由 V2.3.11 Live 輸出反查：White House 直連已成功，但 GDELT 遭 HTTP 429；Google Web 翻譯亦遭 HTTP 429，造成 68 個事件中文欄全空。V2.3.12 將翻譯改為批次請求、GDELT加入5秒以上重試與明確cache降級，並修正市場/產業彙總不應被一般WATCH事件平均或覆寫。

## V2.3.11 三輪交互分析修正版（基於使用者指定 V2.3.9）

- 2026-08-24 Live report 顯示 86 個事件僅 10 個有繁中（11.6%）；大量 `TITLE:FAILED:HTTPError`。根因是免Key Google Web翻譯以 8 workers burst 呼叫、失敗結果還會被記憶體快取。新版改為成功才快取、磁碟持久cache、2 workers、節流、429/5xx retry/backoff、CJK有效性檢查。
- 翻譯前移除 ` - Publisher` 尾碼，翻譯後原樣接回 Publisher，避免來源名稱被翻譯層改寫。
- 新增 White House Official first-party direct URL collector 與免Key GDELT DOC 2.0 direct-publisher URL collector，降低對 Google News RSS 單一聚合通道的依賴。
- GitHub `scheduled_run.py` 現在與 Streamlit UI 同步支援 GDELT、White House，以及有 Key 時的 GNews/NewsAPI；修正排程版永遠不會執行 GNews/NewsAPI 的落差。
- `verification_media` 不再被誤解為獨立 Reuters/AP/Bloomberg adapter：來源健康頁明確分離「Publisher 身分」與「Acquisition Channel」。
- 去重邏輯改為：跨 Publisher 的近似標題保留作獨立交叉驗證；同 Publisher 重複時優先保留 direct URL / first-party 證據，避免 Google redirect 把 GDELT/官方直連覆蓋。
- Truth rendered page 若是 Cloudflare security verification，標記 `ACCESS_DENIED_CLOUDFLARE_CHALLENGE`，不再誤寫 `RENDERED_NO_POSTS`。
- Debug Log ZIP 功能保留：`runtime.log / debug.log / error.log`。


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

## V2.3.8 Live Evidence corrections

V2.3.8 is a corrective release based on the 2026-08-12 17:44 Streamlit Cloud run. It fixes duplicate event fragmentation, the all-zero Materiality outcome for verified high-severity events, false Taiwan-candidate fallback when no material event exists, misleading Truth Official `NO_POSTS` status under HTTP 403, and adds richer downloadable source-layer debug evidence.

### V2.3.9 中英文同步
- 首頁與事件頁保留英文原標題，旁邊同步顯示繁體中文，不以翻譯取代證據原文。
- `TRANSLATION_PROVIDER=AUTO`：若已設定 `AI_API_URL/AI_API_KEY/AI_MODEL`，優先使用相容 LLM；否則使用 Google Web translation best-effort。翻譯服務失敗不會改變事件聚類、重大性分數或英文原文。
- 可用環境變數：`TRANSLATION_ENABLED`、`TRANSLATION_PROVIDER`、`TRANSLATION_API_URL`、`TRANSLATION_TIMEOUT_SECONDS`、`TRANSLATION_MAX_WORKERS`。
- `GOOGLE_WEB_UNOFFICIAL` 為免金鑰 best-effort 路徑，服務可用性不保證；正式企業環境可設定 LLM endpoint。


## V2.3.16 — 2026-08-25 12:36 Live root-cause fix
- Live translation regressed to 0/101 because both Google Web and MyMemory public providers were throttled. Adds explicit Google → MyMemory → Lingva public three-stage failover, success-only provider evidence, and clearer failure status.
- Adds Federal Register no-key API and U.S. Treasury official press-release pages as direct first-party sources to reduce Google RSS acquisition concentration.
- GDELT timeout reduced for a 5-minute monitoring workload; persisted circuit/degraded behavior retained.
- Truth rendered-browser layer is optional and disabled by default. Chromium/Playwright are removed from default deployment because Live logs show ~257 MB download / ~995 MB installed footprint while Truth still returns a Cloudflare challenge. Static HTML + manual review remain.
