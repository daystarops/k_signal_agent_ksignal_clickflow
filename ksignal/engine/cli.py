from __future__ import annotations
import json,os
from pathlib import Path
from .corpus import generate_issue_001
from .seed import generate_issue_002
from .orchestrator import SourceOrchestrator
from .provider_health import ProviderHealthStore
from .velocity import compute_velocity
from ksignal.render import CreativeRenderer
def run_command(args):
    cmd=args.engine_command
    if cmd=="source-seed":
        source,ig=generate_issue_002(); print(json.dumps([x for x in source if not args.lane or x["lane"]==args.lane],ensure_ascii=False)); return
    if cmd=="source-engine-test": print(json.dumps(generate_issue_001())); return
    if cmd=="provider-health":
        store=ProviderHealthStore(); apify=SourceOrchestrator().apify; store.update(apify.provider_id,apify.status,apify.failure_mode); print(store.path.read_text()); return
    if cmd=="instagram-discover":
        orch=SourceOrchestrator(); seeds=[{"issue_id":args.issue,"hashtag":x,"candidate_id":"instagram"} for x in (args.hashtags or "").split(",") if x] or [{"issue_id":args.issue,"hashtag":"kbeauty","candidate_id":args.lane or "instagram"}]; nodes=[]
        for s in seeds: nodes.extend(orch.discover_instagram(s,args.max_items)); print(json.dumps([n.model_dump(mode="json") for n in nodes],indent=2)); return
    if cmd=="signal-velocity": print(compute_velocity(args.issue,args.window,{"sources":[],"platforms":[],"metrics":{}}).model_dump_json(indent=2)); return
    if cmd=="creative-render": print(CreativeRenderer().render(args.issue,args.candidate,{"working_headline":args.candidate,"lane":"signal"}).model_dump_json(indent=2)); return
    if cmd in {"source-discover","source-capture","source-briefs","source-engine-run","instagram-capture","creative-engine-run","audit"}: generate_issue_002(); print(json.dumps({"command":cmd,"issue":args.issue,"status":"pending","failure_mode":None})); return
