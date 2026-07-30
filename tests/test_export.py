from datetime import datetime, timezone
from pathlib import Path
from openpyxl import load_workbook
from trump_monitor.collectors.sample import SampleAdapter
from trump_monitor.config import AppConfig
from trump_monitor.engine import TrumpEventEngine
from trump_monitor.exporters.excel_exporter import export_excel


def test_excel_six_sheets(tmp_path):
    root=Path(__file__).resolve().parents[1]
    result=TrumpEventEngine(AppConfig(mode="SAMPLE"),[SampleAdapter(root/"data/sample_items.json")]).run(datetime(2026,7,28,0,0,tzinfo=timezone.utc))
    out=export_excel(result,tmp_path/"report.xlsx")
    wb=load_workbook(out,read_only=True)
    assert wb.sheetnames == ["01_三日重大摘要","02_新聞明細","03_市場影響","04_產業影響","05_GTC事件輸出","06_方法與限制","07_台股候選","08_V2功能與限制","09_來源健康"]
