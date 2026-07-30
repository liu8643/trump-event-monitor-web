from datetime import datetime, timezone
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/'src'))
from trump_monitor.config import load_config
from trump_monitor.engine import TrumpEventEngine
from trump_monitor.collectors.google_news_rss import GoogleNewsRssAdapter
from trump_monitor.collectors.cnbc import CnbcNewsAdapter
from trump_monitor.collectors.truth_social import TruthTimelineCollector,TruthManualImportAdapter,TruthSearchIndexAdapter
from trump_monitor.exporters.excel_exporter import export_excel
from trump_monitor.exporters.json_exporter import export_json
from trump_monitor.exporters.html_exporter import export_html
from trump_monitor.exporters.docx_exporter import export_docx
from trump_monitor.exporters.pdf_exporter import export_pdf
from trump_monitor.watchlist import update_watchlist
from trump_monitor.repository import EventRepository
cfg=load_config(ROOT/'config.yaml'); adapters=[]
if cfg.truth_official_timeline_enabled:
    adapters.append(TruthTimelineCollector(cfg.truth_profile_url,cfg.truth_account,timeout=cfg.truth_official_timeline_timeout,max_pages=cfg.truth_official_timeline_max_pages))
adapters.extend([TruthManualImportAdapter(ROOT/cfg.truth_manual_import_path,cfg.truth_account),TruthSearchIndexAdapter(cfg.truth_account)])
if cfg.cnbc_enabled: adapters.append(CnbcNewsAdapter(timeout=cfg.cnbc_timeout))
adapters.append(GoogleNewsRssAdapter())
r=TrumpEventEngine(cfg,adapters).run(datetime.now(timezone.utc)); out=ROOT/'output'; out.mkdir(exist_ok=True)
export_excel(r,out/'latest.xlsx'); export_json(r,out/'latest.json'); export_html(r,out/'latest.html'); export_docx(r,out/'latest.docx'); export_pdf(r,out/'latest.pdf')
j,c=update_watchlist(r.taiwan_candidates,out); r.watchlist_paths=[str(j),str(c)]
EventRepository(out/'trump_events.sqlite3').save_run(r)
print(r.status,r.run_id,len(r.events),len(r.taiwan_candidates))
