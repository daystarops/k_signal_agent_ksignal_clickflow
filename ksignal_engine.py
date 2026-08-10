"""Standalone K-Signal Engine V1 command entry point."""
import argparse
from ksignal.engine.cli import run_command
def main():
    p=argparse.ArgumentParser(); sub=p.add_subparsers(required=True)
    commands=["source-seed","source-discover","source-capture","source-briefs","source-engine-run","instagram-discover","instagram-capture","creative-render","creative-engine-run","source-engine-test","audit","provider-health","signal-velocity"]
    for command in commands:
        q=sub.add_parser(command); q.add_argument("--issue",default="002"); q.add_argument("--lane",choices=["beauty","food","society","fandom","sports"]); q.add_argument("--lanes"); q.add_argument("--candidate",default="card_candidate_01"); q.add_argument("--provider",choices=["apify","browser","http","all"],default="all"); q.add_argument("--max-items",type=int,default=20); q.add_argument("--window",choices=["24h","72h","7d"],default="24h"); q.add_argument("--hashtags",default=""); q.add_argument("--urls"); q.add_argument("--auto-queue",action="store_true"); q.add_argument("--auto-queue-threshold",type=float,default=7.5); q.set_defaults(engine_command=command,func=run_command)
    args=p.parse_args(); args.func(args)
if __name__=="__main__": main()
