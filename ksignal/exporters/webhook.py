from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            rows.append({"raw": line})
    return rows


def build_payload(output_dir: str | Path = "outputs") -> dict[str, Any]:
    out = Path(output_dir)
    brief_path = out / "brief.md"
    cards_path = out / "signal_cards.jsonl"
    raw_path = out / "raw_items.jsonl"
    html_path = out / "newsletter.html"

    brief = brief_path.read_text(encoding="utf-8") if brief_path.exists() else ""
    cards = _read_jsonl(cards_path)
    raw_items = _read_jsonl(raw_path)
    html = html_path.read_text(encoding="utf-8") if html_path.exists() else ""

    image_paths: list[str] = []
    screenshot_paths: list[str] = []
    for c in cards:
        image_paths.extend(c.get("image_paths") or [])
        screenshot_paths.extend(c.get("screenshot_paths") or [])

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "brief_markdown": brief,
        "newsletter_html": html,
        "cards": cards,
        "raw_items_count": len(raw_items),
        "card_count": len(cards),
        "image_paths": list(dict.fromkeys(image_paths)),
        "screenshot_paths": list(dict.fromkeys(screenshot_paths)),
        "source": "k_signal_agent_ksignal_clickflow",
    }


def push_webhook(webhook_url: str | None = None, output_dir: str | Path = "outputs", timeout: int = 60) -> dict[str, Any]:
    webhook_url = webhook_url or os.getenv("WEBHOOK_URL") or os.getenv("N8N_WEBHOOK_URL")
    if not webhook_url:
        raise RuntimeError("Missing WEBHOOK_URL or N8N_WEBHOOK_URL in .env")

    payload = build_payload(output_dir)
    with httpx.Client(timeout=timeout) as client:
        resp = client.post(webhook_url, json=payload)
        resp.raise_for_status()
        text = resp.text[:2000]
        try:
            body: Any = resp.json()
        except Exception:
            body = text
        return {
            "status_code": resp.status_code,
            "response": body,
            "sent_card_count": payload["card_count"],
            "sent_brief_chars": len(payload["brief_markdown"]),
        }
