# V2.1.0
- Integrated deep-report narrative with automated evidence/event pipeline.
- Fixed category-only clustering, airport/AI false positive, Truth search-index evidence inflation, weighted market aggregation, GTC rationale and timeline export.

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
