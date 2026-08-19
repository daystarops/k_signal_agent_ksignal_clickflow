"""Manual live probe for the bounded media eligibility layer."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ksignal.engine.media_acquisition import collect_youtube_media, search_wikimedia_commons
from ksignal.engine.media_eligibility import MediaStoryContext, classify_media_eligibility
from ksignal.engine.media_rights import classify_media_rights
from ksignal.models.openai_client import _client


def main() -> int:
    load_dotenv()
    api_key = os.getenv("YOUTUBE_API_KEY")
    client = _client()
    if not api_key or client is None:
        raise RuntimeError("YOUTUBE_API_KEY and OPENAI_API_KEY are required")

    wanted_ids = (
        "vOVWMfnPiu4",  # JTBC News
        "tFcfjgP3BJs",  # JTBC Newsroom
        "nM63FG68CPE",  # YonhapnewsTV
        "dlvgSpzutK4",  # smaller attributable channel
        "iosYCnw5HaY",  # smaller channel
    )
    youtube = collect_youtube_media(wanted_ids, api_key).candidates
    commons = search_wikimedia_commons("임지민", result_count=5).candidates
    selected = youtube + commons
    story = MediaStoryContext(
        headline="NC pitcher Lim Ji-min hospitalized after a line drive struck his face",
        context=(
            "NC Dinos pitcher 임지민 was struck in the face by a 178.7 km/h batted ball "
            "during the ninth inning at Sajik Baseball Stadium on August 14, 2026. He was "
            "taken to a hospital, diagnosed with a jaw fracture, and scheduled for surgery. "
            "The delayed ambulance access also raised questions about stadium safety response."
        ),
        temporal_context="The incident occurred on 2026-08-14; follow-up reporting ran afterward.",
    )
    batch = classify_media_eligibility(story, selected, client)
    for item, assessment in zip(selected, batch.results):
        source = item.creator or item.source or "unknown"
        rights = classify_media_rights(item, assessment)
        eligibility = "/".join(
            (
                assessment.relevance_status.value,
                assessment.provenance_status.value,
                assessment.temporal_status.value,
                str(assessment.eligible).lower(),
            )
        )
        print(
            "\t".join(
                (
                    item.title or item.provider_asset_id,
                    f"{item.provider}/{source}",
                    eligibility,
                    item.license_code or "unknown",
                    str(item.embeddable).lower() if item.embeddable is not None else "n/a",
                    rights.disposition.value,
                    rights.reason,
                )
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
