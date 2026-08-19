"""Deterministic final media selection after eligibility and rights gates."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ksignal.article_package import ArticlePackage
from ksignal.engine.media_acquisition import MediaCandidate
from ksignal.engine.media_eligibility import (
    MediaEligibilityAssessment,
    MediaProvenanceStatus,
    MediaTemporalStatus,
    media_candidate_id,
)
from ksignal.engine.media_rights import MediaRightsAssessment, MediaRightsDisposition


class _FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class MediaEditorialUtility(_FrozenModel):
    candidate_id: str
    story_relevance: int = Field(ge=0, le=10)
    explanatory_value: int = Field(ge=0, le=10)
    video_materially_better: bool = False
    rationale: str

    @field_validator("candidate_id", "rationale")
    @classmethod
    def require_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("editorial utility fields must not be empty")
        return value


class MediaSelectionScore(_FrozenModel):
    candidate_id: str
    selectable: bool
    total: int
    eligibility: int
    rights: int
    provenance: int
    temporal_fit: int
    story_relevance: int
    explanatory_value: int
    video_event_value: int
    use_mode: MediaRightsDisposition
    rationale: str


class MediaSelectionAssessment(_FrozenModel):
    story_id: str
    article_slug: str
    primary_candidate_id: str | None
    supporting_candidate_ids: tuple[str, ...]
    rejected_candidate_ids: tuple[str, ...]
    scores: tuple[MediaSelectionScore, ...]


_RIGHTS_SCORE = {
    MediaRightsDisposition.REUSE_OK: 25,
    MediaRightsDisposition.EMBED_ONLY: 20,
    MediaRightsDisposition.LINK_ONLY: 0,
    MediaRightsDisposition.MANUAL_REVIEW: 0,
    MediaRightsDisposition.REJECT: 0,
}
_PROVENANCE_SCORE = {
    MediaProvenanceStatus.AUTHORITATIVE: 15,
    MediaProvenanceStatus.ATTRIBUTABLE_SECONDARY: 10,
    MediaProvenanceStatus.UNCLEAR: 0,
    MediaProvenanceStatus.PROBLEMATIC: 0,
}
_TEMPORAL_SCORE = {
    MediaTemporalStatus.CURRENT: 10,
    MediaTemporalStatus.CONTEXTUAL: 6,
    MediaTemporalStatus.UNKNOWN: 3,
    MediaTemporalStatus.MISMATCH: 0,
}
_SELECTABLE = {MediaRightsDisposition.REUSE_OK, MediaRightsDisposition.EMBED_ONLY}


def select_editorial_media(
    article: ArticlePackage,
    candidates: tuple[MediaCandidate, ...],
    eligibility: tuple[MediaEligibilityAssessment, ...],
    rights: tuple[MediaRightsAssessment, ...],
    utility: tuple[MediaEditorialUtility, ...],
    *,
    supporting_limit: int = 2,
    minimum_primary_score: int = 85,
) -> MediaSelectionAssessment:
    """Rank one story's candidates without making new factual or rights judgments."""
    if supporting_limit < 0 or supporting_limit > 4:
        raise ValueError("supporting_limit must be between 0 and 4")
    if minimum_primary_score < 1 or minimum_primary_score > 108:
        raise ValueError("minimum_primary_score must be between 1 and 108")
    candidate_ids = tuple(media_candidate_id(item) for item in candidates)
    for label, values in (
        ("eligibility", tuple(item.candidate_id for item in eligibility)),
        ("rights", tuple(item.candidate_id for item in rights)),
        ("utility", tuple(item.candidate_id for item in utility)),
    ):
        if values != candidate_ids:
            raise ValueError(f"{label} candidate order does not match candidates")

    scored: list[tuple[int, int, MediaCandidate, MediaSelectionScore]] = []
    for index, (candidate, eligible, right, editorial) in enumerate(
        zip(candidates, eligibility, rights, utility)
    ):
        selectable = eligible.eligible and right.disposition in _SELECTABLE
        video_event = (
            8 if candidate.media_type == "video" and editorial.video_materially_better else 0
        )
        components = {
            "eligibility": 30 if eligible.eligible else 0,
            "rights": _RIGHTS_SCORE[right.disposition],
            "provenance": _PROVENANCE_SCORE[eligible.provenance_status],
            "temporal_fit": _TEMPORAL_SCORE[eligible.temporal_status],
            "story_relevance": editorial.story_relevance,
            "explanatory_value": editorial.explanatory_value,
            "video_event_value": video_event,
        }
        total = sum(components.values()) if selectable else 0
        reason = editorial.rationale
        if not eligible.eligible:
            reason = f"Rejected by eligibility: {eligible.reason}"
        elif right.disposition not in _SELECTABLE:
            reason = f"Not selectable for rendering: {right.disposition.value}. {right.reason}"
        score = MediaSelectionScore(
            candidate_id=media_candidate_id(candidate),
            selectable=selectable,
            total=total,
            use_mode=right.disposition,
            rationale=reason,
            **components,
        )
        scored.append((total, index, candidate, score))

    ordered = sorted(scored, key=lambda item: (-item[0], item[1]))
    selectable_rows = [item for item in ordered if item[3].selectable]
    primary = (
        selectable_rows[0][3].candidate_id
        if selectable_rows and selectable_rows[0][3].total >= minimum_primary_score
        else None
    )
    supporting = tuple(
        item[3].candidate_id
        for item in selectable_rows[1:] if primary
        if item[2].media_type == "image"
        and item[3].use_mode == MediaRightsDisposition.REUSE_OK
    )[:supporting_limit]
    rejected = tuple(item[3].candidate_id for item in scored if not item[3].selectable)
    return MediaSelectionAssessment(
        story_id=article.story_id,
        article_slug=article.article_slug,
        primary_candidate_id=primary,
        supporting_candidate_ids=supporting,
        rejected_candidate_ids=rejected,
        scores=tuple(item[3] for item in scored),
    )
