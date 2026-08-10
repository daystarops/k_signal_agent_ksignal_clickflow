from ksignal.engine.models import CaptureVersion,SourceNode
from ksignal.engine.differential import compare_captures
from ksignal.engine.temporal import TemporalStore
def test_diff():
    a=CaptureVersion(provider="x",access_status="captured",extracted_text="a",visible_metrics={"commentsCount":1}); b=CaptureVersion(provider="x",access_status="denied",extracted_text="b",visible_metrics={"commentsCount":3}); d=compare_captures(a,b); assert d["text_delta"] and d["comment_delta"]==2 and d["access_status_delta"]==["captured","denied"]
def test_append(tmp_path):
    n=SourceNode(issue_id="1",candidate_id="c",url="https://x"); s=TemporalStore(tmp_path/"x.duckdb"); a=s.append_capture(n,CaptureVersion(provider="x",access_status="captured")); b=s.append_capture(n,CaptureVersion(provider="x",access_status="captured")); assert a["capture_count"]==1 and b["capture_count"]==2 and a["current_capture_id"]!=b["current_capture_id"]; s.close()

