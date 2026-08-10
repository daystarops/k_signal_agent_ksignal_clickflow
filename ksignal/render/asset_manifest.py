import json
from pathlib import Path
def write_manifest(manifest,path):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True); path.write_text(manifest.model_dump_json(indent=2),encoding="utf-8"); return path

