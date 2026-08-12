from __future__ import annotations
from pathlib import Path
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase import pdfmetrics
from trump_monitor.models import RunResult

def export_pdf(result: RunResult,path: str|Path):
    out=Path(path); out.parent.mkdir(parents=True,exist_ok=True)
    font='Helvetica'
    for fp in ['/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc','/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf']:
        if Path(fp).exists():
            try: pdfmetrics.registerFont(TTFont('CJK',fp)); font='CJK'; break
            except Exception: pass
    c=canvas.Canvas(str(out),pagesize=A4); w,h=A4; y=h-50; c.setFont(font,14); c.drawString(40,y,'Trump 72-hour Event Report / 川普72小時事件報告'); y-=28
    c.setFont(font,9); c.drawString(40,y,f'Run ID: {result.run_id} / Status: {result.status}'); y-=24
    for e in result.events:
        lines=[('★'*e.score.importance+' '+e.topic)[:78],('中文: '+(e.topic_zh or '翻譯未取得'))[:78],('EN: '+e.summary)[:100],('中文摘要: '+(e.summary_zh or '翻譯未取得'))[:100],f'{e.category} / confidence {e.score.confidence:.0%} / materiality {e.materiality_score}/100 / {e.battle_action}']
        for line in lines:
            if y<60: c.showPage(); c.setFont(font,9); y=h-50
            c.drawString(40,y,line); y-=16
        y-=8
    c.save(); return out
