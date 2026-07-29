# Trump 72-hour Event Monitor v1.2.0

Streamlit Web app for Trump/Truth Social event monitoring and market-impact analysis.

## Formal source priority
1. Truth Social primary source: licensed API, manual import, search-index discovery
2. Reuters / AP / Bloomberg verification
3. Google News RSS supplement
4. NewsAPI / GNews supplement

## Run
```bash
python -m pip install -r requirements.txt
streamlit run app/streamlit_app.py
```

## Optional secrets
`TRUTH_API_BASE_URL`, `TRUTH_API_TOKEN`, `GNEWS_API_KEY`, `NEWSAPI_API_KEY`.

Without a licensed Truth API, paste/export posts into `data/truth_manual_posts.json`, or use search-index discovery. The system never substitutes Sample data in ONLINE/AUTO mode.

## GitHub Release
```bash
git tag v1.2.0
git push origin v1.2.0
```
