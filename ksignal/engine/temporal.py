from __future__ import annotations
import json
from pathlib import Path
import duckdb
from .differential import compare_captures
from .models import CaptureVersion, SourceNode

SCHEMA=["create table if not exists sources(source_id varchar, canonical_url varchar, first_seen_at timestamp, last_seen_at timestamp, capture_count integer)","create table if not exists captures(capture_id varchar, source_id varchar, captured_at timestamp, access_status varchar, content_hash varchar, screenshot_hash varchar, payload json)","create table if not exists source_metrics(capture_id varchar, metrics json)","create table if not exists source_text_snapshots(capture_id varchar, text varchar)","create table if not exists source_failures(capture_id varchar, failure_mode varchar)","create table if not exists signals(signal_id varchar, payload json)","create table if not exists signal_velocity(signal_id varchar, updated_at timestamp, payload json)","create table if not exists claim_support(claim_id varchar, source_id varchar)","create table if not exists provider_runs(provider varchar, status varchar, failure_mode varchar, timestamp timestamp, elapsed_ms integer)"]
class TemporalStore:
    def __init__(self,path="outputs/source_engine/ksignal_intelligence.duckdb"):
        self.path=Path(path); self.path.parent.mkdir(parents=True,exist_ok=True); self.db=duckdb.connect(str(self.path)); [self.db.execute(sql) for sql in SCHEMA]
    def append_capture(self,node:SourceNode,capture:CaptureVersion):
        previous=node.capture_versions[-1] if node.capture_versions else None; diff=compare_captures(previous,capture); node.capture_versions.append(capture); node.current_access_status=capture.access_status; node.last_captured_at=capture.captured_at
        self.db.execute("insert into captures values (?,?,?,?,?,?,?)",[capture.version_id,node.source_id,capture.captured_at,capture.access_status.value,capture.content_hash,capture.screenshot_hash,json.dumps(capture.model_dump(mode="json"))]); self.db.execute("insert into source_metrics values (?,?)",[capture.version_id,json.dumps(capture.visible_metrics)]); self.db.execute("insert into source_text_snapshots values (?,?)",[capture.version_id,capture.extracted_text]);
        return {"first_seen_at":node.first_seen_at.isoformat(),"last_seen_at":capture.captured_at.isoformat(),"capture_count":len(node.capture_versions),"prior_capture_id":previous.version_id if previous else None,"current_capture_id":capture.version_id,**diff}
    def close(self): self.db.close()

