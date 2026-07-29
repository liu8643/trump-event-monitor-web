import json
from datetime import datetime, timezone
from trump_monitor.collectors.truth_social import TruthManualImportAdapter, TruthOfficialApiAdapter


def test_truth_manual_import(tmp_path):
    p=tmp_path/"truth.json"
    p.write_text(json.dumps([{"published_at":"2026-07-28T01:00:00Z","text":"Direct Truth post","url":"https://truthsocial.com/@realDonaldTrump/posts/1"}]),encoding="utf-8")
    rows=TruthManualImportAdapter(p).collect(datetime(2026,7,27,tzinfo=timezone.utc),datetime(2026,7,29,tzinfo=timezone.utc))
    assert len(rows)==1 and rows[0].source_tier==1 and rows[0].source_type=="DIRECT_POST"

class Resp:
    status_code=200
    def json(self): return {"posts":[{"id":"1","created_at":"2026-07-28T01:00:00Z","content":"<p>Direct post</p>","url":"https://truthsocial.com/@realDonaldTrump/posts/1"}]}

def test_truth_api_shape(monkeypatch):
    monkeypatch.setattr("requests.get",lambda *a,**k:Resp())
    rows=TruthOfficialApiAdapter("https://api.example.test",token="x").collect(datetime(2026,7,27,tzinfo=timezone.utc),datetime(2026,7,29,tzinfo=timezone.utc))
    assert rows[0].acquisition_method=="LICENSED_API" and rows[0].direct_quote
