from datetime import datetime, timezone
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from trump_monitor.collectors.sample import SampleAdapter
from trump_monitor.config import AppConfig
from trump_monitor.engine import TrumpEventEngine
from trump_monitor.exporters.excel_exporter import export_excel
from trump_monitor.exporters.json_exporter import export_json
from trump_monitor.exporters.html_exporter import export_html
from trump_monitor.exporters.docx_exporter import export_docx
from trump_monitor.exporters.pdf_exporter import export_pdf
from trump_monitor.repository import EventRepository
from trump_monitor.watchlist import update_watchlist

cfg = AppConfig(mode="SAMPLE")
result = TrumpEventEngine(cfg, [SampleAdapter(ROOT / "data/sample_items.json")]).run(datetime(2026,7,28,0,0,tzinfo=timezone.utc))
out = ROOT / "output"; out.mkdir(exist_ok=True)
paths = [
    export_excel(result, out / "smoke_report_SAMPLE_ONLY.xlsx"),
    export_json(result, out / "smoke_events_SAMPLE_ONLY.json"),
    export_html(result, out / "smoke_report_SAMPLE_ONLY.html"),
    export_docx(result, out / "smoke_report_SAMPLE_ONLY.docx"),
    export_pdf(result, out / "smoke_report_SAMPLE_ONLY.pdf"),
]
j,c=update_watchlist(result.taiwan_candidates,out); result.watchlist_paths=[str(j),str(c)]; paths += [j,c]
repo=EventRepository(out/'smoke_events.sqlite3'); repo.save_run(result)
assert result.data_mode == "SAMPLE"
assert all(p.exists() and p.stat().st_size > 0 for p in paths)
assert repo.list_events(result.run_id) and repo.list_sources(result.run_id) and repo.list_impacts(result.run_id)
assert paths[3].read_bytes()[:2] == b'PK'
assert paths[4].read_bytes()[:5] == b'%PDF-'
print(f"SMOKE SAMPLE PASS: {result.run_id}, events={len(result.events)}, status={result.status}, artifacts={len(paths)}")
