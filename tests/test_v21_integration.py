from datetime import datetime,timezone
from trump_monitor.models import RawItem
from trump_monitor.classifier import classify_category,classify_source_type
from trump_monitor.clustering import cluster_items
from trump_monitor.ai_service import heuristic_analyze


def item(i,title,body="",method="GOOGLE_NEWS_RSS"):
    return RawItem(raw_item_id=str(i),source_name="Reuters",publisher_group="Reuters",source_type="MEDIA_REPORT",published_at=datetime.now(timezone.utc),title=title,body=body,url=f"https://x/{i}",acquisition_method=method)

def test_airport_not_ai_semiconductor():
    x=item(1,'Trump calls Dulles a terrible airport')
    assert classify_category(x)!="AI／半導體"
    assert heuristic_analyze(x.title,x.body).category!="AI／半導體"

def test_truth_search_index_not_direct():
    x=item(1,'Donald J. Trump - Truth Social',method="SEARCH_INDEX")
    x.publisher_group="Truth Social"; x.source_name="Truth Social (Search Index)"
    assert classify_source_type(x)=="UNCONFIRMED"

def test_same_category_distinct_events_not_merged():
    a=item(1,'Trump discusses Iran ceasefire and oil supply')
    b=item(2,'Trump mourns senator at Washington funeral')
    cats={"1":"地緣政治／能源","2":"地緣政治／能源"}
    assert len(cluster_items([a,b],cats))==2

def test_related_sources_cluster():
    a=item(1,'Trump discusses Iran ceasefire and oil supply')
    b=item(2,'Iran ceasefire talks affect global oil supply')
    cats={"1":"地緣政治／能源","2":"地緣政治／能源"}
    assert len(cluster_items([a,b],cats))==1

def test_truth_posting_spree_is_social_not_semiconductor():
    x=item(1,'Donald Trump goes on Truth Social posting spree with AI images')
    assert classify_category(x)=="社群訊號／TMTG"
    assert heuristic_analyze(x.title,x.body).category=="社群訊號／TMTG"
