from __future__ import annotations

import re
from collections import defaultdict
from trump_monitor.models import RawItem

STOPWORDS={"trump","donald","says","said","new","news","reuters","ap","associated","press","the","and","for","with","from","that","this","his","her","are","was","were","will","over","after","before","how","as","at","on","in","to","of","a","an","us","u.s"}


def _tokens(item: RawItem) -> set[str]:
    text=f"{item.title} {item.body[:600]}".lower()
    words=set(re.findall(r"[a-z0-9]{3,}|[\u4e00-\u9fff]{2,}", text))
    return {w for w in words if w not in STOPWORDS}


def _similar(a: RawItem,b: RawItem,threshold: float=.23) -> bool:
    ta,tb=_tokens(a),_tokens(b)
    if not ta or not tb: return False
    inter=len(ta & tb); union=len(ta | tb)
    if inter>=3 and inter/max(1,min(len(ta),len(tb)))>=.45: return True
    return inter/union>=threshold


def _event_family(item: RawItem) -> str:
    """Return a narrow semantic family for headlines that use very different wording.

    This is deliberately conservative: a family is emitted only when an action/entity
    combination is distinctive enough to represent the same real-world event. It is
    used to bridge category drift (for example SECURITY vs GEOPOLITICS), not to merge
    every story about Iran, tariffs, or elections.
    """
    text=f"{item.title} {item.body[:800]}".lower()
    # 2026 real-world regression: secret/decoy plane change under a security threat was
    # described as catering truck / military jet / secret flight / switch planes.
    transport = re.search(r"\b(plane|planes|flight|fly|flew|jet|air force one|catering truck|decoy)\b", text)
    security = re.search(r"\b(secret|secretly|switch(?:ed)? planes?|ruse|decoy|security|secret service|threat|risk)\b", text)
    if transport and security and re.search(r"\b(trump|president)\b", text):
        return "PRESIDENT_SECURITY_FLIGHT_CHANGE"

    # Distinguish an actual Iran military/economic-options escalation from generic Iran commentary.
    if re.search(r"\biran\b", text) and re.search(r"\b(military option|military options|hit them really hard|strike|attack|economic(?:ally)? fail|fail economically)\b", text):
        return "IRAN_ESCALATION_OPTIONS"

    if re.search(r"\bmedicaid\b|\bchip\b", text) and re.search(r"gender[- ]affirming|transgender", text):
        return "MEDICAID_GENDER_CARE_POLICY"
    return ""


def cluster_items(items: list[RawItem], categories: dict[str,str]) -> list[tuple[str,list[RawItem]]]:
    """Group sources into distinct real-world events.

    Stage 1 groups narrow cross-category event families. Stage 2 clusters remaining
    rows within category by meaningful token similarity. This prevents both failure
    modes: broad category buckets and duplicate stories split by wording/category.
    """
    groups: list[tuple[str,list[RawItem]]]=[]
    consumed: set[str]=set()
    families: dict[str,list[RawItem]]=defaultdict(list)
    for item in items:
        family=_event_family(item)
        if family: families[family].append(item)
    for family, rows in families.items():
        if len(rows) < 2:
            continue
        # Use the category of the strongest/most specific row. Security wins over geo
        # for presidential protection incidents; otherwise use modal category.
        cats=[categories[x.raw_item_id] for x in rows]
        if "總統安全／國安" in cats and family.startswith("PRESIDENT_SECURITY"):
            category="總統安全／國安"
        else:
            category=max(set(cats), key=cats.count)
        groups.append((category, sorted(rows,key=lambda x:x.published_at)))
        consumed.update(x.raw_item_id for x in rows)

    by_cat: dict[str,list[RawItem]]=defaultdict(list)
    for item in items:
        if item.raw_item_id not in consumed:
            by_cat[categories[item.raw_item_id]].append(item)
    for category, rows in by_cat.items():
        rows=sorted(rows,key=lambda x:x.published_at)
        clusters: list[list[RawItem]]=[]
        for item in rows:
            placed=False
            for cluster in clusters:
                if any(_similar(item,other) for other in cluster):
                    cluster.append(item); placed=True; break
            if not placed: clusters.append([item])
        groups.extend((category,c) for c in clusters)
    return groups
