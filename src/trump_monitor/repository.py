from __future__ import annotations
from pathlib import Path
import sqlite3, json
from trump_monitor.models import RunResult
SCHEMA="""
CREATE TABLE IF NOT EXISTS source_runs(run_id TEXT PRIMARY KEY,started_at TEXT,completed_at TEXT,status TEXT,payload_json TEXT);
CREATE TABLE IF NOT EXISTS events(run_id TEXT,event_id TEXT,topic TEXT,category TEXT,score REAL,confidence REAL,last_seen TEXT,PRIMARY KEY(run_id,event_id));
CREATE TABLE IF NOT EXISTS sources(run_id TEXT,event_id TEXT,raw_item_id TEXT,source_name TEXT,url TEXT,published_at TEXT,content_status TEXT,PRIMARY KEY(run_id,raw_item_id));
CREATE TABLE IF NOT EXISTS impacts(run_id TEXT,event_id TEXT,asset TEXT,final_score INTEGER,confidence REAL);
CREATE TABLE IF NOT EXISTS watchlist(run_id TEXT,ticker TEXT,name TEXT,score REAL,action TEXT,reasons TEXT,PRIMARY KEY(run_id,ticker));
"""
class EventRepository:
    def __init__(self,path):
        self.path=Path(path); self.path.parent.mkdir(parents=True,exist_ok=True)
        with sqlite3.connect(self.path) as c: c.executescript(SCHEMA)
    def save_run(self,result:RunResult):
        with sqlite3.connect(self.path) as c:
            c.execute("INSERT OR REPLACE INTO source_runs VALUES(?,?,?,?,?)",(result.run_id,result.started_at.isoformat(),result.completed_at.isoformat(),result.status,result.model_dump_json()))
            c.execute("DELETE FROM events WHERE run_id=?",(result.run_id,)); c.execute("DELETE FROM sources WHERE run_id=?",(result.run_id,)); c.execute("DELETE FROM impacts WHERE run_id=?",(result.run_id,)); c.execute("DELETE FROM watchlist WHERE run_id=?",(result.run_id,))
            for e in result.events:
                c.execute("INSERT INTO events VALUES(?,?,?,?,?,?,?)",(result.run_id,e.event_id,e.topic,e.category,e.score.final_score,e.score.confidence,e.last_seen.isoformat()))
                for s in e.sources: c.execute("INSERT OR REPLACE INTO sources VALUES(?,?,?,?,?,?,?)",(result.run_id,e.event_id,s.raw_item_id,s.source_name,s.url,s.published_at.isoformat(),s.content_status))
                for i in e.impacts: c.execute("INSERT INTO impacts VALUES(?,?,?,?,?)",(result.run_id,e.event_id,i.asset,i.final_score,i.confidence))
            for r in result.taiwan_candidates: c.execute("INSERT OR REPLACE INTO watchlist VALUES(?,?,?,?,?,?)",(result.run_id,r["ticker"],r["name"],r["score"],r["action"],r["reasons"]))
    def list_runs(self,limit=30):
        with sqlite3.connect(self.path) as c:
            c.row_factory=sqlite3.Row; return [dict(x) for x in c.execute("SELECT run_id,started_at,completed_at,status FROM source_runs ORDER BY started_at DESC LIMIT ?",(limit,)).fetchall()]
    def load_run(self,run_id):
        with sqlite3.connect(self.path) as c:
            row=c.execute("SELECT payload_json FROM source_runs WHERE run_id=?",(run_id,)).fetchone(); return RunResult.model_validate_json(row[0]) if row else None
