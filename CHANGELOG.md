
## V2.3.17 — 2026-08-25 14:01 Live root-cause fix
- 14:01 Production Run showed 108/108 network translations failed even after Google→MyMemory→Lingva. Adds `LOCAL_RULE_ZH_TW` as a deterministic offline Traditional-Chinese reading layer so the Chinese column no longer collapses to blank when all public providers are throttled. It is explicitly labeled `SUCCESS:LOCAL_RULE_PARTIAL`; English remains authoritative evidence.
- Translation reporting now distinguishes full/network translation from `LOCAL_PARTIAL` quality instead of treating every nonblank Chinese string as equivalent.
- GDELT ReadTimeout/transport failures now open the persisted degraded-source circuit and return cache/degraded state instead of throwing `SourceError` traceback on every run.
- Retains V2.3.16 Federal Register, U.S. Treasury, lightweight Truth Rendered disablement, clustering and Materiality fixes.
## 2.3.15 - 2026-08-25
- 依 11:51 Live Run（TRUMP-RUN-20260825-115155）做三輪交互分析。
- 翻譯：確認 Google 429 Circuit → MyMemory fallback 103/103 成功；新增 Taiwan terminology normalization（特朗普→川普），修正 runtime log 的 primary/effective provider 語意。
- GDELT：公開 429 改為持久化 Circuit/快速 degraded fallback；預設 GDELT_RETRIES=1，避免每次 Run 約 52 秒等待；有窗內 cache 時使用明確 CACHE acquisition。
- 事件聚類：新增 CANADA_50_AUTO_TARIFF_ACTION，合併同一加拿大 50% 汽車關稅政策公告的跨媒體碎裂群。
- Materiality：正式 anti-Iran sanctions action +8；Supreme Court/mail-voting election ruling +12；context penalty 改為 cluster-dominant 才套用。
- 分類融合：specific deterministic category 不再被 generic AI `其他／一般政治` 覆蓋。
- Source Health：新增 Adapter 耗時秒數；方法頁新增總執行時間。
- 新增 V2.3.15 Live regression tests；完整 pytest/compile/smoke 驗證。

## 2.3.14 - 2026-08-25
- 修正 GitHub Actions #60：`test_translation_failure_not_persisted_in_memory_cache` 與 `test_google_batch_translation_reduces_requests` 在全套測試下因 translation circuit global state 洩漏而失敗。
- 新增 `tests/conftest.py` autouse fixture：每個 test 前後清除 translation memory cache、Google/MyMemory circuit、request throttle timestamp。
- CI 預設 `TRANSLATION_ENABLED=false` / fallback OFF，避免任何非翻譯專測誤打 public endpoint；翻譯專測自行 monkeypatch 開啟。
- CI matrix 設 `fail-fast:false`，Python 3.11/3.14 無論其中一個失敗都完整執行，提升診斷性。
- Production 翻譯 Circuit Breaker、MyMemory fallback、GDELT soft-limit、移民分類與重大性邏輯均保留不回退。
- 修正 pytest/coverage 額外揭露的 SQLite ResourceWarning：repository 的 connection context 原先只 commit/rollback、不保證 close；改為明確 transactional close，避免長時間 Streamlit 歷史查詢累積連線handle。

## 2.3.13 - 2026-08-25
- 以 11:04 Live Run 與可下載 Debug ZIP 做第三輪現場反查：103 unique translations 全失敗、GDELT HTTP200 非JSON解析失敗、Run耗時約6分32秒。
- 翻譯新增Google 429 Circuit Breaker：第一次429即停止同provider後續批次，避免每批重試造成數分鐘延遲；AUTO無LLM時加入 MyMemory public fallback，Provider/Status明確保留。
- GDELT 對 HTTP200/plain-text rate-limit 或非JSON回應不再直接JSON解析例外；依>=5.2秒重試，最終可使用72h窗內明確標示的cache。
- 新增「移民／邊境政策」分類與deterministic guard，修正實際報告中deported/immigration與H-1B新聞被落入錯誤/一般類別。
- 修正 model_version 仍殘留 V2311 前綴的版本追溯錯誤，統一為 V2.3.13。
- 08功能頁新增翻譯Provider實況，讓中文覆蓋率與實際fallback provider可稽核。

## 2.3.12 - 2026-08-25
- 以 09:34 Live Run 重新三輪交互分析：68 events / 3 material、White House 3筆成功、GDELT HTTP 429、中文翻譯全數 HTTP 429。
- Google Web 翻譯改成小批次 marker 翻譯，將每標題一請求降為每批一請求；保留成功才cache與跨Run persistent cache。
- GDELT 遵守至少5秒 429 retry，支援成功payload cache；live 429時可在72h窗內以明確 CACHE acquisition 狀態降級。
- 市場影響頁改由真正重大事件加權聚合，避免大量 WATCH 事件把重大衝擊平均成0。
- 產業影響頁修正 last-write-wins，改為重大事件跨事件加權彙總。
- 功能限制頁的中英文同步驗收改為 runtime coverage，低於80%標示 DEGRADED，不再固定顯示PASS。


## 2.3.11 - 2026-08-25
- Three-round live evidence review from TRUMP-RUN-20260824-182701.
- Translation resilience: persistent success cache, conservative concurrency, retry/backoff, detailed failure status, publisher-name preservation.
- Added White House Official direct collector and GDELT DOC no-key direct-link collector.
- Scheduled runner now includes the same optional GNews/NewsAPI paths as Streamlit UI.
- Dedup preserves cross-publisher corroboration and prefers direct evidence URLs within the same publisher.
- Source health separates publisher coverage from acquisition channel.
- Cloudflare rendered challenge no longer reported as NO_POSTS.
# V2.3.8 (2026-08-12) — Live Evidence Corrective Release

- Based strictly on the deployed V2.3.7 source and the 2026-08-12 17:44 live run evidence.
- Fix cross-category duplicate fragmentation with conservative event-family clustering for presidential security flight-change coverage and other narrow event signatures.
- Add semantic severity bonus to Materiality so verified military/security actions can clear the 65 gate without relying on accidental duplicate count.
- Remove the contradictory candidate fallback: Taiwan candidates are now produced only from `is_material=True` events.
- Correct Truth Official status: HTTP 403 / ACCESS_DENIED is no longer reported as `NO_POSTS`; search-index fallback is explicitly labeled.
- Expand downloadable debug evidence with source observation layer/status/evidence-quality and degraded-source warning log lines.
- Live regression tests added for the 17:44 failure modes.

## 2.3.5
- 修正 Playwright 只有套件但缺 Chromium 執行檔：新增 packages.txt、系統 Chromium 偵測與 GitHub Workflow 安裝。
- Static HTML 遇到 Cloudflare challenge 改為精簡紀錄，不再把整段 challenge script 寫入報表。
- 補上第四層 MANUAL_REVIEW_AVAILABLE 明確紀錄。
- 首頁來源健康摘要新增「部分來源」，避免將 Truth Official 的部分狀態混入成功來源。

# V2.3.4
- Truth Official 四層來源：JSON、Rendered HTML、Static HTML、人工查閱備註。
- Static page shell會保存但不進Event Engine。
- 新增SourceObservation與Excel/UI追溯。
- Rendered HTML採可選Playwright，無瀏覽器時明示RENDERER_NOT_AVAILABLE。

# V2.3.2
- Truth Official Timeline改為優先使用已知且可設定的realDonaldTrump account ID，避免先呼叫容易被WAF拒絕的accounts/lookup端點。
- 失敗狀態分開標示ACCOUNT_LOOKUP與ACCOUNT_STATUSES，並保留HTTP狀態與Cloudflare診斷資訊。
- 原有授權API、人工匯入、Search Index與所有媒體來源完整保留。

## 2.3.0 - 2026-07-30
- Added a homepage source-health dashboard for Truth Official, Truth Search, Reuters, AP, Bloomberg, CNBC, Google RSS, NewsAPI and GNews.
- Added per-source count, health state, coverage bar, role and detailed raw status.
- Distinguished SUCCESS, NO_DATA, FAILED and NOT_CONFIGURED instead of relying only on the overall PARTIAL status.
- Reused the same source-health table on the Source Settings page and kept raw engineering dictionaries in an expander.
- Added regression tests for publisher-level counts and source-state classification.

## 2.2.3 - 2026-07-30
- Corrected misleading ONLINE sidebar: first-hand Truth status is now based on the actual run.
- Preserved detailed source failure reasons in source_status, Truth status and Excel source-health notes.
- Corrected default schema fallback and GTC report title to gtc.trump_event.v2.2.
- Replaced deprecated Streamlit use_container_width arguments.
- Cleaned release package caches and generated output.

# 2.2.1 - 2026-07-30

- Restore V2.1 regex word-boundary classification so `airport` no longer triggers the `ai` keyword.
- Restore Truth Social/TMTG priority over AI/semiconductor for posting-spree and AI-image stories.
- Restore Truth Search Index as `UNCONFIRMED`, Tier 4, `SUPPLEMENT`, confidence 0.58.
- Add back `clustering.py` and `test_v21_integration.py` so the release package is self-contained.
- Preserve the V2.2 Truth Social Official Timeline collector and all previous sources.

# 2.2.0 - 2026-07-30
- Added `TruthTimelineCollector` as the highest-priority Truth Social Official source.
- Uses configured official profile URL and the same-host public JSON timeline endpoints.
- Sorts posts by publication time and filters strictly to the configured 72-hour window.
- Preserves licensed API, manual import, search index, Google RSS, GNews and NewsAPI behavior.
- Adds explicit source health/status and regression tests.

# Changelog

## 2.0.0
- Full-text status and AI summaries
- Taiwan candidate engine and GTC WatchList files
- Word/PDF exports
- Expanded historical SQLite schema
- Five-minute UI refresh and scheduled workflow

## 2.0.1 - 2026-07-29 V2功能到位修正版
- 修正報表中心未顯示 Word、PDF、GTC WatchList 下載按鈕。
- 新增 Truth Social 人工 JSON 匯入與全文/摘要狀態明示。
- 將規則式摘要標記為 EXTRACTIVE_SNIPPET，避免冒充生成式 AI 摘要。
- 新增歷史執行搜尋與事件、來源、市場影響、WatchList 回溯頁。
- Scheduled Monitor 同步輸出 Excel/JSON/HTML/Word/PDF/WatchList 並保存 SQLite。
- 擴充 Smoke Test 驗證 7 種輸出及歷史資料庫。

## 2.2.2
- 確認原 CNBC 資料不是獨立 Adapter，而是由 Google News RSS 的 `<source>CNBC</source>` 間接取得。
- 新增 `CnbcNewsAdapter`，沿用無金鑰 Google News RSS，但限制來源為 CNBC，提供獨立 source_status/source_counts。
- 保留一般 Google News RSS，交由既有去重流程排除重複。
- UI、來源設定、排程與 Excel 新增 CNBC 狀態；新增 `09_來源健康`。
- 來源零筆狀態改為 `NO_DATA:0`，與失敗 `FAILED:*` 分開。

## 2.3.1 - 2026-07-30
- Reconciled deployed GitHub source with the V2.3.0 formal release.
- Fixed app/streamlit_app.py remaining at V2.2.2 and missing the homepage source-health dashboard.
- Restored dynamic Truth Official status and Source Settings health table.
- Removed generated caches/output and restored .gitignore/.env.example.

## 2.3.7 — V2.3.5 baseline corrective release
- Based strictly on V2.3.5 source package; does not reuse the prior separately-produced V2.4.0 package.
- Activates existing event clustering module in the production engine instead of category-wide aggregation.
- Adds deterministic security and healthcare/social-policy guardrails to prevent CHIP/Medicaid false semiconductor classification and secret-flight category splits.
- Adds 0–100 materiality gate (BLACK/RED/ORANGE/YELLOW/WATCH) and explicit `is_material` marker.
- Fixes AP News publisher alias in source-health counts.
- Adds persistent rotating runtime/debug/error logs and downloadable Debug Log ZIP in Streamlit UI.
- Fixes date-dependent SAMPLE repository regression test by pinning the intended sample evaluation time.

## V2.3.9 — 2026-08-12 — English + 繁體中文同步
- 新增 `translation.py`：英文新聞標題/摘要翻譯繁體中文；AUTO 優先已設定的相容 LLM，否則 Google Web best-effort；有 cache、timeout、parallel worker 與 Debug Log。
- 原始英文永遠保留；翻譯欄位獨立存在，翻譯內容不參與去重、事件聚類、重大性與市場評分。
- 修正 V2.3.8 `ai_summary_zh` 在 Rule fallback 時其實塞英文摘錄的語意錯誤；翻譯失敗時中文欄位留空並明確標示狀態。
- Streamlit 首頁、事件中心、事件分析、新聞明細、Truth貼文、GTC預覽同步顯示 English + 中文。
- Excel/Word/PDF/HTML/JSON 同步新增/輸出雙語欄位；GTC machine schema 保持原22欄不變以維持相容性。
- 修正 Streamlit 可信度 ProgressColumn：0.766 不再顯示為 1%，改為 77%。
- Debug Log 新增 translation batch success/provider 記錄。


## V2.3.16 — 2026-08-25 12:36 Live root-cause fix
- Live translation regressed to 0/101 because both Google Web and MyMemory public providers were throttled. Adds explicit Google → MyMemory → Lingva public three-stage failover, success-only provider evidence, and clearer failure status.
- Adds Federal Register no-key API and U.S. Treasury official press-release pages as direct first-party sources to reduce Google RSS acquisition concentration.
- GDELT timeout reduced for a 5-minute monitoring workload; persisted circuit/degraded behavior retained.
- Truth rendered-browser layer is optional and disabled by default. Chromium/Playwright are removed from default deployment because Live logs show ~257 MB download / ~995 MB installed footprint while Truth still returns a Cloudflare challenge. Static HTML + manual review remain.

## V2.3.18 — 2026-08-25
- Fixed a production clustering regex bug where `50%` could not match because a word-boundary was placed after `%`.
- Added narrow event families for Supreme Court mail-voting rulings and Iran `Operation Economic Outcast` official actions.
- Added event-context market impact regime for tariff easing/suspension versus tariff escalation.
- Fixed `Iranian` classification so official Iran policy rows do not fall into generic politics.
- Improved LOCAL_RULE_ZH_TW templates for Canada retaliatory tariffs and Operation Economic Outcast.
- Translation logs now separate full machine/public translation from local-partial fallback counts.
- Added V2.3.18 live regression tests for the 14:29 production findings.
