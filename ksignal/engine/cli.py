from __future__ import annotations
import json,os,sys
from pathlib import Path
from .corpus import generate_issue_001
from .seed import generate_issue_002
from .orchestrator import SourceOrchestrator
from .provider_health import ProviderHealthStore
from .velocity import compute_velocity
from ksignal.render import CreativeRenderer

ENGINE_COMMANDS = (
    "source-seed",
    "source-discover",
    "source-capture",
    "source-briefs",
    "source-engine-run",
    "instagram-discover",
    "instagram-capture",
    "creative-render",
    "creative-engine-run",
    "source-engine-test",
    "audit",
    "provider-health",
    "signal-velocity",
)


def register_engine_commands(subparsers):
    for command in ENGINE_COMMANDS:
        parser=subparsers.add_parser(command)
        parser.add_argument("--issue",default="002")
        parser.add_argument("--lane",choices=["beauty","food","society","fandom","sports"])
        parser.add_argument("--lanes")
        parser.add_argument("--candidate",default="card_candidate_01")
        parser.add_argument("--provider",choices=["apify","browser","http","all"],default="all")
        parser.add_argument("--max-items",type=int,default=20)
        parser.add_argument("--window",choices=["24h","72h","7d"],default="24h")
        parser.add_argument("--hashtags",default="")
        parser.add_argument("--urls")
        parser.add_argument("--auto-queue",action="store_true")
        parser.add_argument("--auto-queue-threshold",type=float,default=7.5)
        parser.set_defaults(engine_command=command,func=run_command)


def run_command(args):
    cmd=args.engine_command
    if cmd=="source-seed":
        source,ig=generate_issue_002(); reconfigure=getattr(sys.stdout,"reconfigure",None)
        if reconfigure is not None: reconfigure(encoding="utf-8")
        print(json.dumps([x for x in source if not args.lane or x["lane"]==args.lane],ensure_ascii=False)); return
    if cmd=="source-engine-test": print(json.dumps(generate_issue_001())); return
    if cmd=="provider-health":
        store=ProviderHealthStore(); apify=SourceOrchestrator().apify; store.update(apify.provider_id,apify.status,apify.failure_mode); print(store.path.read_text()); return
    if cmd=="instagram-discover":
        orch=SourceOrchestrator(); seeds=[{"issue_id":args.issue,"hashtag":x,"candidate_id":"instagram"} for x in (args.hashtags or "").split(",") if x] or [{"issue_id":args.issue,"hashtag":"kbeauty","candidate_id":args.lane or "instagram"}]; nodes=[]
        for s in seeds: nodes.extend(orch.discover_instagram(s,args.max_items)); print(json.dumps([n.model_dump(mode="json") for n in nodes],indent=2)); return
    if cmd=="signal-velocity": print(compute_velocity(args.issue,args.window,{"sources":[],"platforms":[],"metrics":{}}).model_dump_json(indent=2)); return
    if cmd=="creative-render": print(CreativeRenderer().render(args.issue,args.candidate,{"working_headline":args.candidate,"lane":"signal"}).model_dump_json(indent=2)); return
    if cmd in {"source-discover","source-capture","source-briefs","source-engine-run","instagram-capture","creative-engine-run","audit"}: generate_issue_002(); print(json.dumps({"command":cmd,"issue":args.issue,"status":"pending","failure_mode":None})); return
