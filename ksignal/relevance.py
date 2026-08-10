"""Deterministic, explainable article discovery for K-Signal."""
from __future__ import annotations

from datetime import datetime, timezone
import unicodedata
from typing import Any, Iterable


DEFAULT_ALIASES = {
    "k\ub9ac\uadf8": "k league",
    "\ube4c\ub9ac": "billlie",
    "\ub9b0\uac00\ub4dc": "lingard",
    "\ud32c\ub364": "fandom",
    "\uc2a4\ud3ec\uce20": "sports",
    "fc\uc11c\uc6b8": "fc seoul",
}
INELIGIBLE_STATUSES = {"draft", "held", "withdrawn", "unpublished"}


def normalize(value: Any, aliases: dict[str, str] | None = None) -> str:
    """NFKC/case/whitespace normalization with optional canonical aliases."""
    text = " ".join(unicodedata.normalize("NFKC", str(value or "")).casefold().split())
    mapping = {normalize(k, {}): normalize(v, {}) for k, v in (aliases or DEFAULT_ALIASES).items()}
    return mapping.get(text, text)


def normalized_ids(values: Iterable[Any] | None, aliases: dict[str, str] | None = None) -> list[str]:
    return sorted({item for value in (values or []) if (item := normalize(value, aliases))})


def enrich_card(card: dict[str, Any], editorial_order: int | None = None,
                aliases: dict[str, str] | None = None) -> dict[str, Any]:
    """Return a public-safe record with stable discovery fields; display labels stay intact."""
    result = dict(card)
    if editorial_order is not None:
        result.setdefault("editorial_order", editorial_order)
    result.setdefault("status", "published")
    result.setdefault("lane", result.get("lane_label", "").split(" / ")[0])
    result.setdefault("lane_label", result.get("lane", ""))
    result.setdefault("lane_slug", normalize(result.get("lane", "")).replace(" ", "-"))
    result.setdefault("public_summary", result.get("dek", ""))
    result.setdefault("dek", result.get("public_summary", ""))
    result.setdefault("thumbnail", result.get("hero_image", ""))
    result["normalized_topic_ids"] = normalized_ids(result.get("topic_tags"), aliases)
    result["normalized_entity_ids"] = normalized_ids(result.get("entity_tags"), aliases)
    result["normalized_keyword_ids"] = normalized_ids(result.get("search_keywords"), aliases)
    result["source_platform_id"] = normalize(result.get("source_platform"), aliases)
    result["source_type_id"] = normalize(result.get("source_type"), aliases)
    return result


def is_eligible(card: dict[str, Any], current_card_id: str) -> bool:
    status = normalize(card.get("status"))
    return (
        card.get("card_id") != current_card_id
        and status == "published"
        and status not in INELIGIBLE_STATUSES
        and bool(str(card.get("article_path") or "").strip())
    )


def score_candidate(current: dict[str, Any], candidate: dict[str, Any],
                    aliases: dict[str, str] | None = None) -> dict[str, Any]:
    current = enrich_card(current, aliases=aliases)
    candidate = enrich_card(candidate, aliases=aliases)
    score, reasons = 0, []

    def add(points: int, reason: str) -> None:
        nonlocal score
        score += points
        reasons.append(f"{reason} +{points}")

    same_lane = normalize(current.get("lane_slug") or current.get("lane"), aliases) == normalize(candidate.get("lane_slug") or candidate.get("lane"), aliases)
    if same_lane:
        add(25, "same lane")
    for item in sorted(set(current["normalized_topic_ids"]) & set(candidate["normalized_topic_ids"])):
        add(12, f"shared topic {item}")
    for item in sorted(set(current["normalized_entity_ids"]) & set(candidate["normalized_entity_ids"])):
        add(18, f"shared entity {item}")
    if current["source_platform_id"] and current["source_platform_id"] == candidate["source_platform_id"]:
        add(6, "shared source platform")
    if current["source_type_id"] and current["source_type_id"] == candidate["source_type_id"]:
        add(4, "shared source type")
    if str(current.get("issue_id")) == str(candidate.get("issue_id")):
        add(3, "same issue")
    for item in sorted(set(current["normalized_keyword_ids"]) & set(candidate["normalized_keyword_ids"])):
        add(5, f"shared keyword {item}")
    return {
        "current_card": current.get("card_id"),
        "candidate_card": candidate.get("card_id"),
        "score": score,
        "reasons": reasons,
        "same_lane": same_lane,
    }


def _date_rank(value: Any) -> float:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=timezone.utc).timestamp()
    except (TypeError, ValueError):
        return float("-inf")


def related_signals(current: dict[str, Any], cards: list[dict[str, Any]], limit: int = 2,
                    aliases: dict[str, str] | None = None,
                    overrides: dict[str, Any] | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Select related cards and return (public results, explanations for every candidate)."""
    current_id = str(current.get("card_id"))
    rules = (overrides or {}).get(current_id, {})
    excluded = set(rules.get("pinned_exclude", []))
    pinned = list(rules.get("pinned_include", []))
    scored = []
    for position, card in enumerate(cards):
        if not is_eligible(card, current_id):
            continue
        explanation = score_candidate(current, card, aliases)
        explanation["editorial_override"] = card.get("card_id") in pinned
        explanation["excluded_by_override"] = card.get("card_id") in excluded
        explanation["tie_break"] = {
            "published_at": card.get("published_at"),
            "same_lane": explanation["same_lane"],
            "editorial_override": explanation["editorial_override"],
        }
        scored.append((card, explanation, position))
    allowed = [row for row in scored if row[0].get("card_id") not in excluded]
    allowed.sort(key=lambda row: (
        -row[1]["score"], -_date_rank(row[0].get("published_at")),
        -int(row[1]["same_lane"]), -int(row[1]["editorial_override"]), row[2]
    ))
    # A pinned include is a reversible selection override; normal tie rules order all others.
    pinned_rows = sorted((row for row in allowed if row[0].get("card_id") in pinned), key=lambda row: pinned.index(row[0].get("card_id")))
    ordered = pinned_rows + [row for row in allowed if row not in pinned_rows]
    public = []
    for card, explanation, _ in ordered[:limit]:
        public.append({key: card.get(key) for key in (
            "card_id", "article_path", "lane", "lane_label", "issue_id", "headline",
            "dek", "public_summary", "hero_image", "thumbnail"
        )})
        public[-1]["score"] = explanation["score"]  # internal artifact; strip before public packaging
    return public, [row[1] for row in scored]


def more_from_issue(current: dict[str, Any], cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    eligible = [card for card in cards if is_eligible(card, str(current.get("card_id"))) and str(card.get("issue_id")) == str(current.get("issue_id"))]
    eligible.sort(key=lambda card: (int(card.get("editorial_order", 10**9)), str(card.get("card_id", ""))))
    return [{key: card.get(key) for key in (
        "card_id", "article_path", "editorial_order", "lane", "lane_label", "issue_id",
        "headline", "hero_image", "thumbnail"
    )} for card in eligible]
