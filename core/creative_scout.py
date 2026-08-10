from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote_plus, urlparse


SAFE_IG_RIGHTS = {"owned", "original_source_screenshot", "public_domain", "creative_commons", "press_asset"}


def _candidate(card_id, candidate_type, page_url, title, source_label, rights_status,
               allowed_use, relevance_score, rights_reason, topic_reason, media_url="",
               downloaded_path=""):
    return {
        "card_id": card_id,
        "candidate_type": candidate_type,
        "media_url": media_url,
        "page_url": page_url,
        "title": title,
        "source_domain": urlparse(page_url or media_url).netloc.lower(),
        "source_label": source_label,
        "rights_status": rights_status,
        "allowed_use": allowed_use,
        "relevance_score": float(relevance_score),
        "rights_reason": rights_reason,
        "topic_reason": topic_reason,
        "downloaded_path": downloaded_path,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


def _references(card_id: str):
    refs = {
        "card_01": [
            ("search_result", "https://search.naver.com/search.naver?where=image&query=" + quote_plus("K-pop global fandom discourse"), "Neutral Naver image search", "Naver", "unknown_rights", "reference_only", .45, "Search results do not convey reuse rights.", "Neutral platform/fandom context; no idol is implied."),
            ("search_result", "https://www.bing.com/images/search?q=" + quote_plus("K-pop global fandom discussion neutral"), "Neutral Bing image search", "Bing", "unknown_rights", "reference_only", .40, "Search results do not convey reuse rights.", "Discovery only; prevents attaching an unsupported artist."),
        ],
        "card_02": [
            ("video", "https://www.youtube.com/watch?v=sHRSiPhOT28", "Billlie Work performance — official YouTube reference", "Official YouTube", "official_embed", "article_embed", .96, "Official video may be linked/embedded, never downloaded into IG.", "Directly supports the Work/Zap rollout discussion."),
            ("search_result", "https://search.naver.com/search.naver?where=image&query=" + quote_plus("Billlie Work Zap official"), "Billlie Work / Zap Naver search", "Naver", "unknown_rights", "reference_only", .62, "Search thumbnails have unknown reuse rights.", "Finds topic-specific release context for private review."),
        ],
        "card_03": [
            ("official_page", "https://www.kleague.com/about/competition.do", "K League official competition page", "K League", "unknown_rights", "article_link", .78, "Official page is safe to link; its imagery is not licensed here for reposting.", "Official league context for the fan-made onboarding guide."),
            ("image", "https://commons.wikimedia.org/wiki/File:K_League_Classic_Trophy.png", "K League Classic Trophy", "Wikimedia Commons", "creative_commons", "reference_only", .42, "CC BY-SA 3.0, attribution and share-alike required; only 170px and therefore rejected as low-resolution.", "League-specific but less useful than the captured starter-pack flowchart."),
        ],
        "card_04": [
            ("official_page", "https://www.fcseoul.com/media/newsView?resultPart=News&seq=4076", "FC Seoul official Lingard announcement", "FC Seoul", "unknown_rights", "article_link", .91, "Official press page is linkable; no reusable image license was found.", "Direct official club context for Lingard and FC Seoul."),
            ("official_page", "https://www.fcseoul.com/en", "FC Seoul official site", "FC Seoul", "unknown_rights", "reference_only", .66, "Official ownership does not grant social repost rights.", "Club context only; the source receipt remains safer and more specific."),
        ],
    }
    return refs.get(card_id, [])


def scout_creatives(issue: str, output_root: str | Path = "outputs/issues", allow_unknown_rights: bool = False, mode: str = "safe_public"):
    issue_dir = Path(output_root) / issue
    cards = json.loads((issue_dir / "editorial_cards.json").read_text(encoding="utf-8"))
    candidates = []
    for index, card in enumerate(cards, 1):
        card_id = f"card_{index:02d}"
        source = issue_dir / "media" / f"{card_id}_source.png"
        hero = issue_dir / "media" / f"{card_id}_hero{Path(card['hero_image_path']).suffix}"
        candidates.append(_candidate(card_id, "screenshot", card.get("source_url") or card.get("url", ""),
            "Captured original source receipt", card.get("source_label", "Original Source"),
            "original_source_screenshot", "ig_reel_frame", .99,
            "A labeled screenshot of the inspected source is permitted as a receipt-style visual.",
            "Shows the exact discourse or guide discussed by the card.", downloaded_path=str(source)))
        candidates.append(_candidate(card_id, "image", card.get("source_url") or card.get("url", ""),
            "Captured source hero", card.get("source_label", "Original Source"),
            "original_source_screenshot", "ig_still", .94,
            "Captured from the inspected source and used with source labeling, not as claimed owned art.",
            "Topic-specific context already selected during source inspection.", card.get("hero_image_source_url", ""), str(hero)))
        for ref in _references(card_id):
            candidates.append(_candidate(card_id, *ref))

    for item in candidates:
        permitted = item["rights_status"] in SAFE_IG_RIGHTS and item["allowed_use"] in {"ig_still", "ig_reel_frame"}
        if allow_unknown_rights and item["rights_status"] == "unknown_rights":
            permitted = item["allowed_use"] in {"ig_still", "ig_reel_frame"}
        item["selected_for_ig"] = permitted and item["relevance_score"] >= .8
        item["blocked_from_public_ig"] = not permitted
        if item["rights_status"] == "official_embed":
            item["blocked_from_public_ig"] = True
        if item["selected_for_ig"]:
            item["status"] = "SELECTED"
        elif item["relevance_score"] < .5:
            item["status"] = "LOW_RELEVANCE"
        elif not (item["page_url"] or item["media_url"]):
            item["status"] = "BROKEN"
        elif mode == "creator_mode" and item["rights_status"] in {"official_embed", "unknown_rights"}:
            item["status"] = "STAGED"
        else:
            item["status"] = "NEEDS_REVIEW"

    manifest = {"issue": issue, "mode": mode,
                "policy": "Unknown-rights and external copyrighted video are blocked from public IG export.",
                "candidates": candidates}
    issue_manifest = issue_dir / "creative_manifest.json"
    ig_dir = issue_dir / "distribution_pack" / "instagram"
    ig_dir.mkdir(parents=True, exist_ok=True)
    ig_manifest = ig_dir / "creative_manifest.json"
    payload = json.dumps(manifest, ensure_ascii=False, indent=2)
    issue_manifest.write_text(payload, encoding="utf-8")
    ig_manifest.write_text(payload, encoding="utf-8")
    return manifest, issue_manifest, ig_manifest


def write_creative_sources(manifest: dict, path: Path):
    lines = ["# Creative Sources", "", f"Export mode: **{manifest['mode']}**", "",
             "No external video was downloaded. Official video is reference/embed-only.", ""]
    for item in manifest["candidates"]:
        status = item.get("status", "NEEDS_REVIEW")
        reason = item["rights_reason"]
        if item["blocked_from_public_ig"]:
            reason += " Blocked from public Instagram export."
        lines += [f"## {item['card_id']} — {status}", "",
                  f"- Asset: {item['title']}", f"- Type: {item['candidate_type']}",
                  f"- Rights: `{item['rights_status']}`", f"- Allowed use: `{item['allowed_use']}`",
                  f"- Score: {item['relevance_score']:.2f}", f"- Rights/rejection note: {reason}",
                  f"- Topic note: {item['topic_reason']}", f"- Source: {item['page_url'] or item['media_url']}", ""]
    path.write_text("\n".join(lines), encoding="utf-8")
