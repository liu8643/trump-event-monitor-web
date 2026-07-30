from datetime import datetime, timedelta, timezone
from trump_monitor.collectors.truth_social import TruthTimelineCollector

class Resp:
    def __init__(self,status=200,text="",payload=None): self.status_code=status; self.text=text; self._payload=payload; self.headers={}
    def json(self):
        if self._payload is None: raise ValueError("no json")
        return self._payload
class StaticShellSession:
    def get(self,url,**kwargs):
        if "/api/v1/" in url: return Resp(403)
        return Resp(200,"<html><body>To use this website, please enable JavaScript.</body></html>")

def test_static_shell_is_recorded_but_not_event():
    c=TruthTimelineCollector(session=StaticShellSession(), rendered_html_enabled=False)
    now=datetime.now(timezone.utc)
    rows=c.collect(now-timedelta(hours=72),now)
    assert rows==[]
    assert c.last_status=="STATIC_HTML_PAGE_SHELL"
    assert any(o.status=="STATIC_HTML_PAGE_SHELL" and not o.eligible_for_event_engine for o in c.last_observations)

def test_json_success_is_primary_event():
    now=datetime.now(timezone.utc)
    class JsonSession:
        def get(self,url,**kwargs):
            return Resp(200,payload=[{"id":"1","created_at":now.isoformat(),"content":"<p>Official post text</p>","url":"https://truthsocial.com/@realDonaldTrump/1"}])
    c=TruthTimelineCollector(session=JsonSession(), rendered_html_enabled=False)
    rows=c.collect(now-timedelta(hours=72),now)
    assert len(rows)==1
    assert rows[0].source_tier==1
    assert c.last_status.startswith("SUCCESS_FULL_TEXT")
