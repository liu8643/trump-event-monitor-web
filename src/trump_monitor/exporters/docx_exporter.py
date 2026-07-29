from __future__ import annotations
from pathlib import Path
from docx import Document
from trump_monitor.models import RunResult

def export_docx(result: RunResult,path: str|Path):
    out=Path(path); out.parent.mkdir(parents=True,exist_ok=True); d=Document()
    d.add_heading('川普72小時事件與市場影響報告',0)
    d.add_paragraph(f'Run ID：{result.run_id}｜狀態：{result.status}｜Truth：{result.truth_social_status}')
    for e in result.events:
        d.add_heading('★'*e.score.importance+' '+e.topic,1); d.add_paragraph(e.summary)
        d.add_paragraph(f'類別：{e.category}｜可信度：{e.score.confidence:.0%}｜GTC：{e.battle_action}')
        d.add_paragraph('受惠：'+'、'.join(e.beneficiary_sectors)); d.add_paragraph('受壓：'+'、'.join(e.negative_sectors))
    d.save(out); return out
