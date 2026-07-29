from __future__ import annotations

from pathlib import Path
import sqlite3
from trump_monitor.models import RunResult

SCHEMA = """
CREATE TABLE IF NOT EXISTS source_runs(
  run_id TEXT PRIMARY KEY,
  started_at TEXT NOT NULL,
  completed_at TEXT NOT NULL,
  status TEXT NOT NULL,
  payload_json TEXT NOT NULL
);
"""

class EventRepository:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as conn:
            conn.executescript(SCHEMA)

    def save_run(self, result: RunResult) -> None:
        with sqlite3.connect(self.path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO source_runs VALUES(?,?,?,?,?)",
                (result.run_id,result.started_at.isoformat(),result.completed_at.isoformat(),result.status,result.model_dump_json()),
            )

    def list_runs(self, limit: int = 30) -> list[dict]:
        with sqlite3.connect(self.path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT run_id, started_at, completed_at, status FROM source_runs ORDER BY started_at DESC LIMIT ?",(limit,)).fetchall()
            return [dict(x) for x in rows]
