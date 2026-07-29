# 架構

`SourceAdapter → normalize/deduplicate → classify → score → impact → RunResult → Excel/JSON/HTML/GTC`

核心保護：
- 原始來源保留
- AI 失敗可 Rule-only
- Schema 不符不得匯入 GTC
- Sample/STALE 資料不得產生 BUY_READY
