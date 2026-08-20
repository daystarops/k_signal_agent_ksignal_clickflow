"""Acquire the official poster frame for each already-approved embed-only video.

The homepage must not embed a player, so a video-backed story needs a still image to stand in
for it. The only rights-safe still that already belongs to an approved video is the poster
YouTube itself publishes for that video — the same representation `core/web_searcher.py` already
uses for YouTube candidates (`i.ytimg.com/vi/<id>/…`). Nothing is generated, cropped or
substituted: the poster is downloaded as published and recorded against the manifest entry whose
`video_url` it belongs to, so `video_thumbnail_path` becomes local approved media like any other
hero.

Run once per issue whose manifest has `video_url` set and `video_thumbnail_path` empty.
"""

from __future__ import annotations

import json
import re
import sys
import urllib.request
from pathlib import Path

# Highest published resolution first: not every upload has a maxres frame, and hq is guaranteed.
POSTER_QUALITIES = ("maxresdefault", "hqdefault")
VIDEO_ID = re.compile(r"(?:embed/|v=|youtu\.be/)([A-Za-z0-9_-]{11})")


def _video_id(url: str) -> str:
    match = VIDEO_ID.search(url)
    if not match:
        raise ValueError(f"Not a recognisable YouTube URL, so it has no official poster: {url!r}")
    return match.group(1)


def _download(video_id: str, destination: Path) -> str:
    last_error = ""
    for quality in POSTER_QUALITIES:
        source = f"https://i.ytimg.com/vi/{video_id}/{quality}.jpg"
        try:
            with urllib.request.urlopen(source, timeout=30) as response:
                payload = response.read()
        except Exception as error:  # noqa: BLE001 - reported, then the next quality is tried
            last_error = f"{source}: {error}"
            continue
        # YouTube answers a missing frame with a 120x90 grey placeholder rather than a 404.
        if len(payload) < 4000:
            last_error = f"{source}: placeholder response ({len(payload)} bytes)"
            continue
        destination.write_bytes(payload)
        return source
    raise RuntimeError(f"No official poster could be fetched for {video_id}. Last: {last_error}")


def fetch_posters(issue: str, output_root: str | Path = "outputs/issues") -> list[str]:
    issue_dir = Path(output_root) / issue
    manifest_path = issue_dir / "media" / "media_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    notes: list[str] = []
    for key, entry in manifest.items():
        video = str(entry.get("video_url", ""))
        if not video:
            continue
        existing = str(entry.get("video_thumbnail_path", ""))
        if existing and Path(existing).exists():
            notes.append(f"card {key}: poster already present at {existing}")
            continue
        target = issue_dir / "media" / f"card_{int(key):02d}_poster.jpg"
        source = _download(_video_id(video), target)
        entry["video_thumbnail_path"] = target.as_posix()
        entry["video_thumbnail_source_url"] = source
        notes.append(f"card {key}: {source} -> {target} ({target.stat().st_size} bytes)")
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return notes


if __name__ == "__main__":
    for line in fetch_posters(sys.argv[1] if len(sys.argv) > 1 else "002"):
        print(line)
