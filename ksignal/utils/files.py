from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterable


def slugify(value: str, max_len: int = 80) -> str:
    value = re.sub(r"https?://", "", value.lower())
    value = re.sub(r"[^a-z0-9가-힣]+", "-", value).strip("-")
    return value[:max_len] or "item"


def ensure_dir(path: str | Path) -> Path:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def write_jsonl(path: str | Path, rows: Iterable[object]) -> None:
    p = Path(path)
    ensure_dir(p.parent)
    with p.open("w", encoding="utf-8") as f:
        for row in rows:
            if hasattr(row, "model_dump"):
                row = row.model_dump()
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def append_jsonl(path: str | Path, row: object) -> None:
    p = Path(path)
    ensure_dir(p.parent)
    if hasattr(row, "model_dump"):
        row = row.model_dump()
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def read_jsonl(path: str | Path) -> list[dict]:
    p = Path(path)
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]
