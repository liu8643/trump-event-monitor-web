from __future__ import annotations

from pathlib import Path
from trump_monitor.models import RunResult


def export_json(result: RunResult, path: str | Path) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".tmp")
    tmp.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    tmp.replace(out)
    return out
