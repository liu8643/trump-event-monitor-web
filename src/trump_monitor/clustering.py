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


def cluster_items(items: list[RawItem], categories: dict[str,str]) -> list[tuple[str,list[RawItem]]]:
    """Group sources into distinct events, not merely broad categories.

    Items must share a category and meaningful title/body tokens. Direct Truth posts
    remain separate unless a media item clearly overlaps their content.
    """
    groups: list[tuple[str,list[RawItem]]]=[]
    by_cat: dict[str,list[RawItem]]=defaultdict(list)
    for item in items: by_cat[categories[item.raw_item_id]].append(item)
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
