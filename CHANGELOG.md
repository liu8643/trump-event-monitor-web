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
