from __future__ import annotations

from html import escape
from pathlib import Path
from trump_monitor.models import RunResult


def export_html(result: RunResult, path: str | Path) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    cards = []
    for e in result.events:
        stars = "★" * e.score.importance
        cards.append(f"""
        <section class='card'>
          <h2>{escape(stars)} {escape(e.topic)}</h2>
          <h3>{escape(e.topic_zh or '翻譯未取得')}</h3>
          <p><b>類別：</b>{escape(e.category)}　<b>可信度：</b>{e.score.confidence:.0%}　<b>重大性：</b>{e.materiality_score}/100　<b>GTC：</b>{e.battle_action}</p>
          <p><b>English summary：</b>{escape(e.summary)}</p>
          <p><b>中文摘要：</b>{escape(e.summary_zh or '翻譯未取得')}</p>
          <p><b>受惠：</b>{escape('、'.join(e.beneficiary_sectors))}<br><b>受壓：</b>{escape('、'.join(e.negative_sectors))}</p>
          <p class='meta'>Translation: {escape(e.translation_status)}</p>
        </section>""")
    html = f"""<!doctype html><html lang='zh-Hant'><head><meta charset='utf-8'>
    <title>川普72小時事件報告</title><style>body{{font-family:Arial,'Microsoft JhengHei',sans-serif;max-width:1200px;margin:auto;padding:24px;background:#f4f6f8}}.card{{background:white;padding:18px;margin:14px 0;border-radius:10px;box-shadow:0 1px 5px #bbb}}h1{{color:#17365d}}h3{{color:#385d8a;margin-top:-8px}}.meta{{color:#666;font-size:12px}}</style></head>
    <body><h1>川普72小時事件監控與市場影響｜English + 繁體中文</h1><p>Run ID: {escape(result.run_id)}｜狀態: {escape(result.status)}｜資料模式: {escape(result.data_mode)}｜Truth Social: {escape(result.truth_social_status)}</p><p><b>來源優先順序：</b>{escape(' → '.join(result.source_priority))}</p><p><b>來源狀態：</b>{escape(str(result.source_status))}</p>{''.join(cards)}</body></html>"""
    tmp = out.with_suffix(out.suffix + ".tmp")
    tmp.write_text(html, encoding="utf-8")
    tmp.replace(out)
    return out
