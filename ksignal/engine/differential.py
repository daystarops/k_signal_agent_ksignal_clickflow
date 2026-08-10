from __future__ import annotations
from .models import CaptureVersion

def compare_captures(previous:CaptureVersion|None,current:CaptureVersion):
    if previous is None: return {"changed_since_last_capture":False,"change_summary":["baseline"],"metric_delta":{},"text_delta":False,"comment_delta":0,"access_status_delta":None,"screenshot_hash_delta":False}
    keys=set(previous.visible_metrics)|set(current.visible_metrics); delta={}
    for k in keys:
        a,b=previous.visible_metrics.get(k),current.visible_metrics.get(k)
        if isinstance(a,(int,float)) and isinstance(b,(int,float)) and a!=b: delta[k]=b-a
    text=(previous.content_hash or previous.extracted_text)!=(current.content_hash or current.extracted_text)
    status=previous.access_status.value!=current.access_status.value; shot=previous.screenshot_hash!=current.screenshot_hash
    summary=[]
    if text: summary.append("body_text_changed")
    if delta: summary.append("visible_metrics_changed")
    if status: summary.append(f"{previous.access_status.value}_to_{current.access_status.value}")
    if shot: summary.append("screenshot_hash_changed")
    return {"changed_since_last_capture":bool(summary),"change_summary":summary,"metric_delta":delta,"text_delta":text,"comment_delta":delta.get("commentsCount",delta.get("comment_count",0)),"access_status_delta":[previous.access_status.value,current.access_status.value] if status else None,"screenshot_hash_delta":shot}

