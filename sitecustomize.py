"""Narrow build hook for additive discovery augmentation.

The recovered issue builder remains untouched; the hook runs only after a
successful-looking ``main.py rebuild-issue`` process reaches interpreter exit.
"""
from __future__ import annotations
import atexit
from pathlib import Path
import sys

def _augment_rebuild() -> None:
    args = sys.argv
    if len(args) < 2 or Path(args[0]).name != "main.py" or args[1] != "rebuild-issue":
        return
    try:
        issue = args[args.index("--issue") + 1]
        root = args[args.index("--output-root") + 1] if "--output-root" in args else "outputs/issues"
        from ksignal.discovery import build_discovery
        build_discovery(Path(root) / issue, issue)
    except (ValueError, IndexError, FileNotFoundError):
        return

atexit.register(_augment_rebuild)
