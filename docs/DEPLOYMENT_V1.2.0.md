# GitHub / Streamlit Deployment v1.2.0

1. Upload all project-root files to the private GitHub repository.
2. Streamlit entry point: `app/streamlit_app.py`.
3. Default AUTO mode uses the formal source order:
   Truth Social -> Reuters/AP/Bloomberg -> Google News RSS -> NewsAPI/GNews.
4. Optional GitHub/Streamlit secrets:
   - `TRUTH_API_BASE_URL`
   - `TRUTH_API_TOKEN`
   - `GNEWS_API_KEY`
   - `NEWSAPI_API_KEY`
5. Without a licensed Truth API, use `data/truth_manual_posts.json`; search-index discovery remains enabled.
6. Tag release:
   `git tag v1.2.0 && git push origin v1.2.0`
