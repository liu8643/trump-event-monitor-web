from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import requests
from dateutil import parser as date_parser

from trump_monitor.collectors.base import SourceAdapter, SourceError
from trump_monitor.models import RawItem

class FederalRegisterAdapter(SourceAdapter):
    """Official FederalRegister.gov no-key API for presidential/regulatory actions."""
    name="federal_register"
    endpoint="https://www.federalregister.gov/api/v1/documents.json"
    def __init__(self, timeout:int=10): self.timeout=timeout
    def collect(self,start:datetime,end:datetime)->list[RawItem]:
        params={
            "per_page":100,"order":"newest",
            "conditions[term]":"Trump",
            "conditions[publication_date][gte]":start.date().isoformat(),
            "conditions[publication_date][lte]":end.date().isoformat(),
        }
        try:
            r=requests.get(self.endpoint,params=params,timeout=self.timeout,headers={"User-Agent":"TrumpEventMonitor/2.3.16"})
            r.raise_for_status(); payload=r.json()
        except Exception as exc:
            raise SourceError(f"Federal Register 取得失敗: {type(exc).__name__}") from exc
        results=payload.get("results",[]) if isinstance(payload,dict) else []
        rows=[]
        for rec in results if isinstance(results,list) else []:
            if not isinstance(rec,dict): continue
            title=str(rec.get("title") or "").strip(); url=str(rec.get("html_url") or rec.get("document_number") or "").strip()
            if not title or not url.startswith("http"): continue
            try:
                dt=date_parser.parse(str(rec.get("publication_date") or ""))
                if dt.tzinfo is None: dt=dt.replace(tzinfo=timezone.utc)
                dt=dt.astimezone(timezone.utc)
            except Exception: continue
            # Publication dates are day-resolution; retain rows in the requested calendar window.
            if not (start.date() <= dt.date() <= end.date()): continue
            rid="FR-"+sha256(url.encode("utf-8")).hexdigest()[:16]
            rows.append(RawItem(raw_item_id=rid,source_name="Federal Register",publisher_group="Federal Register",source_type="OFFICIAL_POLICY",published_at=dt,title=title,body=str(rec.get("abstract") or ""),url=url,source_confidence=0.99,source_tier=1,source_role="PRIMARY",acquisition_method="FEDERAL_REGISTER_API_DIRECT_URL",content_status="OFFICIAL_METADATA"))
        self.last_status=f"SUCCESS:{len(rows)}" if rows else "NO_DATA:0"
        return rows
