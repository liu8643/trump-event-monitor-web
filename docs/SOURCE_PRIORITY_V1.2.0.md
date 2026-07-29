# 正式版資料來源優先順序

1. Truth Social 第一手來源：授權 Truth API、人工匯入、搜尋索引發現。
2. Reuters／Associated Press／Bloomberg：交叉驗證。
3. Google News RSS：補充與發現。
4. NewsAPI／GNews：補充。

## TruthCollector 設計
- `TruthOfficialApiAdapter`: 取得授權 API 後啟用。
- `TruthManualImportAdapter`: 匯入使用者取得的原始貼文 JSON。
- `TruthSearchIndexAdapter`: 從搜尋索引發現直接貼文連結與摘要，不直接自動抓取 Truth Social 頁面。

Truth Social 服務條款限制未授權的 bot/script 自動存取，因此本正式版不內建繞過限制的網頁爬蟲。若授權 API 未設定且最近72小時無人工匯入／索引結果，系統顯示 `FAILED_OR_NOT_CONFIGURED` 或 `NO_POSTS_IN_WINDOW`，不以 Sample 替代。
