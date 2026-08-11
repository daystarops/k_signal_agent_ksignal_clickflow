"""Standalone K-Signal Engine V1 command entry point."""
import argparse
from ksignal.engine.cli import register_engine_commands
def main():
    p=argparse.ArgumentParser(); sub=p.add_subparsers(required=True)
    register_engine_commands(sub)
    args=p.parse_args(); args.func(args)
if __name__=="__main__": main()
