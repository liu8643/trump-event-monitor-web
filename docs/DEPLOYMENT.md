# GitHub Web / Release 部署說明

## Web 版

- 主入口：`app/streamlit_app.py`
- Streamlit Cloud Advanced settings：Python 3.11
- Secrets：`GNEWS_API_KEY`、`NEWSAPI_API_KEY`
- 若 Repo 為 Private，需確認 Streamlit Cloud 帳號已取得 Repo 權限。

## Release 版

Tag `v*` 觸發 `.github/workflows/release.yml`：
1. 安裝依賴
2. 執行 pytest
3. 打包完整 source ZIP
4. 產生 SHA256
5. 建立 GitHub Release

## 正式資料來源切換

正式模式需關閉 `config.yaml` 的 `sample_mode`，並提供合法 API key。Truth Social 原始貼文來源只應由官方或授權介面取得。
