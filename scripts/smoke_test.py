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

# Explicit SAMPLE smoke only. Production default remains AUTO/ONLINE.
cfg = AppConfig(mode="SAMPLE")
result = TrumpEventEngine(cfg, [SampleAdapter(ROOT / "data/sample_items.json")]).run(datetime(2026,7,28,0,0,tzinfo=timezone.utc))
out = ROOT / "output"
export_excel(result, out / "smoke_report_SAMPLE_ONLY.xlsx")
export_json(result, out / "smoke_events_SAMPLE_ONLY.json")
export_html(result, out / "smoke_report_SAMPLE_ONLY.html")
assert result.data_mode == "SAMPLE"
print(f"SMOKE SAMPLE PASS: {result.run_id}, events={len(result.events)}, status={result.status}")
