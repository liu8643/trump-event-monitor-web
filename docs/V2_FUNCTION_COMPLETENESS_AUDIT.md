# V2 功能到位查核

## 查核結論
原 V2.0.0 為「部分完成」：核心模組存在，但 UI 與執行鏈未完整接通。

| 功能 | 原版狀態 | 2.0.1 修正後 |
|---|---|---|
| Truth Social 全文 | 授權/人工來源有能力，但 UI 無人工匯入 | 新增 JSON 匯入、全文與 snippet 狀態明示 |
| Reuters/Bloomberg 摘要 | 規則式截取，容易被誤認為 AI 摘要 | 明示 EXTRACTIVE_SNIPPET；設定 LLM 後才是 LLM_ABSTRACTIVE |
| AI 事件分類 | 規則分類 + 可選 LLM | 保留並明示實際 provider |
| 台股受惠分析 | 靜態產業映射候選 | UI 顯示、WATCH Gate 保留 |
| GTC WatchList | 有產檔函式且分析時執行，但 UI 不可下載 | 報表中心可下載 JSON/CSV |
| Word/Excel/PDF | Exporter 存在，但 UI 只提供 Excel/JSON/HTML | 全部一鍵下載 |
| 每5分鐘更新 | 頁面刷新與 GitHub workflow 存在 | Scheduled Run 同步輸出所有報告與資料庫 |
| 歷史查詢回溯 | 只有 Run 列表 | 新增搜尋、批次選取及四類明細/完整 JSON |

## 仍需外部條件
- Truth Social 完整原文：授權 API 或使用者匯入原文；搜尋索引不能視為全文。
- Reuters/Bloomberg 生成式中文摘要：需合法取得的內文與設定相容 LLM 金鑰。
- 台股候選不是即時買點：未接即時行情、成交量、持倉與 GTC DB 前，全部為 WATCH。
- Streamlit Community Cloud SQLite 不是永久儲存。
