"""Manual media-acquisition probe; never selects or downloads candidates."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ksignal.engine.media_acquisition import (
    MediaAcquisitionResult,
    search_openverse,
    search_wikimedia_commons,
    search_youtube_media,
)


QUERY = "임지민"


def _print_summary(name: str, result: MediaAcquisitionResult) -> None:
    print(f"{name}: {len(result.candidates)} candidate(s)")
    for item in result.candidates:
        print(
            f"  {item.media_type} | {item.provider_asset_id} | "
            f"{item.license_code or 'license unavailable'} | "
            f"{item.title or 'title unavailable'} | {item.creator or 'creator unavailable'} | "
            f"{item.published_at.isoformat() if item.published_at else 'date unavailable'} | "
            f"{item.duration_iso8601 or 'duration unavailable'} | "
            f"embeddable={item.embeddable}"
        )
    if result.missing_asset_ids:
        print(f"  missing: {', '.join(result.missing_asset_ids)}")


def _probe(name: str, operation) -> None:
    try:
        _print_summary(name, operation())
    except Exception as exc:
        print(f"{name}: unavailable ({type(exc).__name__})")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query", nargs="?", default=QUERY, help="story or entity query")
    parser.add_argument(
        "--load-dotenv",
        action="store_true",
        help="load YOUTUBE_API_KEY from the repository .env when available",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.load_dotenv:
        from dotenv import load_dotenv

        load_dotenv(Path(__file__).resolve().parents[1] / ".env")

    key = os.environ.get("YOUTUBE_API_KEY")
    if not key:
        print("YouTube: skipped (YOUTUBE_API_KEY is not set)")
    else:
        _probe("YouTube", lambda: search_youtube_media(args.query, key))

    _probe("Wikimedia Commons", lambda: search_wikimedia_commons(args.query, 5))
    _probe("Openverse", lambda: search_openverse(args.query, 5))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
