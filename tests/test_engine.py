from datetime import datetime, timezone
from pathlib import Path
from trump_monitor.collectors.sample import SampleAdapter
from trump_monitor.config import AppConfig
from trump_monitor.engine import TrumpEventEngine


def test_engine_sample():
    root=Path(__file__).resolve().parents[1]
    engine=TrumpEventEngine(AppConfig(mode="SAMPLE"),[SampleAdapter(root/"data/sample_items.json")])
    result=engine.run(datetime(2026,7,28,0,0,tzinfo=timezone.utc))
    assert result.status in {"SUCCESS","PARTIAL"}
    assert result.events
    assert result.schema_version == "gtc.trump_event.v2.1"
