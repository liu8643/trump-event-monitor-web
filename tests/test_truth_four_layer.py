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


class CloudflareSession:
    def get(self,url,**kwargs):
        if "/api/v1/" in url: return Resp(403)
        return Resp(403, "<html><title>Just a moment...</title><body>Enable JavaScript and cookies to continue<script>window._cf_chl_opt={very:'long'}</script></body></html>")

def test_cloudflare_static_html_is_sanitized_and_manual_review_added():
    c=TruthTimelineCollector(session=CloudflareSession(), rendered_html_enabled=False)
    now=datetime.now(timezone.utc)
    rows=c.collect(now-timedelta(hours=72),now)
    assert rows==[]
    static=next(o for o in c.last_observations if o.layer=="STATIC_HTML")
    assert static.status=="ACCESS_DENIED_CLOUDFLARE_CHALLENGE"
    assert "Cloudflare challenge page" in static.displayed_text
    assert "_cf_chl_opt" not in static.displayed_text
    manual=next(o for o in c.last_observations if o.layer=="MANUAL_REVIEW")
    assert manual.status=="MANUAL_REVIEW_AVAILABLE"
    assert not manual.eligible_for_event_engine


class RenderedChallengeLocator:
    def inner_text(self, timeout=0):
        return "truthsocial.com\nPerforming security verification\nThis website uses a security service to protect against malicious bots.\nRay ID: test-ray\nPerformance and Security by Cloudflare"
    def all(self): return []

class RenderedChallengePage:
    def goto(self,*args,**kwargs): return None
    def wait_for_timeout(self,*args,**kwargs): return None
    def locator(self, selector):
        if selector == "body": return RenderedChallengeLocator()
        return RenderedChallengeLocator()

class RenderedChallengeBrowser:
    def new_page(self, **kwargs): return RenderedChallengePage()
    def close(self): return None

class RenderedChallengeChromium:
    def launch(self, **kwargs): return RenderedChallengeBrowser()

class RenderedChallengePW:
    chromium = RenderedChallengeChromium()

class RenderedChallengeContext:
    def __enter__(self): return RenderedChallengePW()
    def __exit__(self,*args): return False

def test_rendered_cloudflare_is_not_mislabeled_as_no_posts(monkeypatch):
    import playwright.sync_api
    monkeypatch.setattr(playwright.sync_api, "sync_playwright", lambda: RenderedChallengeContext())
    c=TruthTimelineCollector(session=CloudflareSession(), static_html_enabled=False, chromium_executable="/usr/bin/chromium")
    now=datetime.now(timezone.utc)
    rows=c.collect(now-timedelta(hours=72),now)
    assert rows==[]
    rendered=next(o for o in c.last_observations if o.layer=="RENDERED_HTML")
    assert rendered.status=="RENDERED_ACCESS_DENIED_CLOUDFLARE_CHALLENGE"
    assert "Cloudflare" in rendered.note
    assert rendered.status!="RENDERED_NO_POSTS"
