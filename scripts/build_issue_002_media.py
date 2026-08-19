"""Build auditable Issue 002 media selections and the legacy render manifest."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ksignal.article_package import ArticlePackage
from ksignal.engine.media_acquisition import collect_youtube_media
from ksignal.engine.media_eligibility import MediaStoryContext, classify_media_eligibility
from ksignal.engine.media_rights import classify_media_rights
from ksignal.engine.media_selection import MediaEditorialUtility, select_editorial_media
from ksignal.models.openai_client import _client


ISSUE_DIR = ROOT / "outputs" / "issues" / "002"
CONFIG = {
    "card_01": {
        "ids": ("E3s-Ug1Tcdw", "jfx829qFSCg"),
        "temporal": "The finished story concerns Korean market coverage published in August 2026.",
        "utility": {
            "E3s-Ug1Tcdw": (9, 9, True, "Current established business-news coverage directly explains the Samjeon-nix market framing."),
            "jfx829qFSCg": (10, 8, True, "The owner-approved source video directly supplies the headline framing, subject to provenance classification."),
        },
    },
    "card_02": {
        "ids": ("uNZ-zcH2ckA", "vOVWMfnPiu4", "tFcfjgP3BJs"),
        "temporal": "The injury occurred on 2026-08-14 and response reporting followed immediately.",
        "utility": {
            "uNZ-zcH2ckA": (10, 10, True, "KNN reporting directly documents the delayed ambulance entry and stadium response at the center of the finished story."),
            "vOVWMfnPiu4": (9, 8, True, "JTBC directly documents the injury event but gives less emphasis to the stadium-response follow-up."),
            "tFcfjgP3BJs": (9, 8, True, "JTBC Newsroom directly documents the injury and diagnosis but is less specific to ambulance access."),
        },
    },
    "card_03": {
        "ids": ("ZqtIfkiNDlQ", "8ZVw7nzfwo8"),
        "temporal": "The finished story reports an August 2026 K-goods travel-shopping development; older material may only be contextual.",
        "utility": {
            "ZqtIfkiNDlQ": (5, 5, False, "A generic older souvenir clip is contextual and does not document the specific reported development."),
            "8ZVw7nzfwo8": (6, 5, False, "The clip is closer to foreign-tourist K-goods shopping but remains older secondary context, not the reported event."),
        },
    },
    "card_04": {
        "ids": ("w0Wmiu6AjXk", "SpRsFLWrOxI"),
        "temporal": "The finished story covers BigBang's August 2026 twentieth-anniversary activity and new single.",
        "utility": {
            "w0Wmiu6AjXk": (10, 10, True, "Current YonhapnewsTV coverage directly explains the anniversary and new-single activity in the finished story."),
            "SpRsFLWrOxI": (9, 8, True, "Current Dispatch footage directly depicts an anniversary event but explains less of the broader story."),
        },
    },
}


def main() -> int:
    load_dotenv(ROOT / ".env")
    api_key = os.getenv("YOUTUBE_API_KEY")
    client = _client()
    if not api_key or client is None:
        raise RuntimeError("YOUTUBE_API_KEY and OPENAI_API_KEY are required")
    media_dir = ISSUE_DIR / "media"
    media_dir.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, dict] = {}
    audit: dict[str, dict] = {}
    for position, (slot, config) in enumerate(CONFIG.items(), 1):
        package = ArticlePackage.model_validate_json(
            (ISSUE_DIR / "article_packages" / f"{slot}.json").read_text(encoding="utf-8")
        )
        candidates = collect_youtube_media(config["ids"], api_key).candidates
        batch = classify_media_eligibility(
            MediaStoryContext.from_article_package(
                package, temporal_context=str(config["temporal"])
            ),
            candidates,
            client,
        )
        rights = tuple(
            classify_media_rights(candidate, eligible)
            for candidate, eligible in zip(candidates, batch.results)
        )
        utilities = tuple(
            MediaEditorialUtility(
                candidate_id=f"youtube:{candidate.provider_asset_id}",
                story_relevance=config["utility"][candidate.provider_asset_id][0],
                explanatory_value=config["utility"][candidate.provider_asset_id][1],
                video_materially_better=config["utility"][candidate.provider_asset_id][2],
                rationale=config["utility"][candidate.provider_asset_id][3],
            )
            for candidate in candidates
        )
        selection = select_editorial_media(
            package, candidates, batch.results, rights, utilities
        )
        by_id = {f"youtube:{item.provider_asset_id}": item for item in candidates}
        selected = by_id.get(selection.primary_candidate_id or "")
        selected_rights = next(
            (item for item in rights if item.candidate_id == selection.primary_candidate_id),
            None,
        )
        if selected and selected_rights:
            manifest[str(position)] = {
                "hero_image_path": "",
                "hero_source_url": "",
                "hero_credit": selected.creator or selected.source or "",
                "video_url": selected.embed_url or "",
                "video_thumbnail_path": "",
                "media_confidence": "high",
                "media_reason": next(
                    item.rationale for item in selection.scores
                    if item.candidate_id == selection.primary_candidate_id
                ),
                "source_screenshot_path": "",
                "rights_status": selected_rights.disposition.value,
                "source_url": selected.landing_url,
                "candidate_id": selection.primary_candidate_id,
            }
        else:
            manifest[str(position)] = {
                "hero_image_path": "", "hero_source_url": "", "hero_credit": "",
                "video_url": "", "video_thumbnail_path": "", "media_confidence": "none",
                "media_reason": "Unresolved: no candidate cleared the deterministic selection threshold.",
                "source_screenshot_path": "", "rights_status": "unresolved",
                "source_url": "", "candidate_id": "",
            }
        audit[slot] = {
            "article": package.model_dump(mode="json"),
            "candidates": [item.model_dump(mode="json") for item in candidates],
            "eligibility": batch.model_dump(mode="json"),
            "rights": [item.model_dump(mode="json") for item in rights],
            "utility": [item.model_dump(mode="json") for item in utilities],
            "selection": selection.model_dump(mode="json"),
        }
    (media_dir / "media_selection.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (media_dir / "media_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({key: value["candidate_id"] or "UNRESOLVED" for key, value in manifest.items()}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
