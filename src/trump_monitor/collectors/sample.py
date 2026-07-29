from __future__ import annotations

from datetime import datetime
from pathlib import Path
import json

from trump_monitor.collectors.base import SourceAdapter
from trump_monitor.models import RawItem


class SampleAdapter(SourceAdapter):
    name = "sample"

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def collect(self, start: datetime, end: datetime) -> list[RawItem]:
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        items = [RawItem.model_validate({**x, "source_tier": x.get("source_tier", 4), "source_role": x.get("source_role", "SUPPLEMENT"), "acquisition_method": x.get("acquisition_method", "SAMPLE")}) for x in payload]
        return [x for x in items if start <= x.published_at <= end]
