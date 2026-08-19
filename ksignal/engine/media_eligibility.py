"""Story and provenance eligibility for acquired media candidates.

Rights compatibility and final media ordering deliberately belong to later gates.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from ksignal.article_package import ArticlePackage
from ksignal.engine.media_acquisition import MediaCandidate
from ksignal.engine.models import StrEnum


DEFAULT_MEDIA_ELIGIBILITY_MODEL = "gpt-5-mini"
DUPLICATE_MEDIA_CANDIDATE_ID = "DUPLICATE_MEDIA_CANDIDATE_ID"
MEDIA_ELIGIBILITY_COUNT_MISMATCH = "MEDIA_ELIGIBILITY_COUNT_MISMATCH"
MEDIA_ELIGIBILITY_CANDIDATE_ORDER_MISMATCH = "MEDIA_ELIGIBILITY_CANDIDATE_ORDER_MISMATCH"


MEDIA_ELIGIBILITY_INSTRUCTIONS = """
You are a constrained K-Signal media eligibility classifier. Judge two independent
dimensions using only the supplied finished-story context and candidate metadata.
Do not browse, use outside knowledge, rank candidates, or decide copyright or license
compatibility.

RELEVANCE: Decide whether the media actually depicts, documents, or materially explains
the supplied story, entity, event, or development. A matching name, generic visual,
sport, team, or topic is insufficient. Reject a different person with the same name and
unrelated clips. Use hold when metadata leaves a material identity/event ambiguity.

TEMPORAL COHERENCE: current means the media corresponds to the story period; contextual
means older or otherwise non-current media remains genuinely useful background;
mismatch means its time materially contradicts the represented story; unknown means the
metadata cannot establish timing. Older media is not automatically irrelevant or
ineligible.

PROVENANCE: Characterize only what the supplied attribution evidence supports.
authoritative means an apparent original, official, or established reporting source;
attributable_secondary means a clearly identified secondary source whose origin is
traceable; unclear means aggregation/reupload or origin cannot be established;
problematic means metadata supplies an explicit provenance concern. Do not infer trust
from a brand list, and do not classify syndication or evidence independence.

eligible is a strict derived contract: true exactly when relevance_status is pass,
provenance_status is authoritative or attributable_secondary, and temporal_status is
current, contextual, or unknown. A temporal mismatch must never be eligible. Return one result per candidate
in input order, reproduce candidate_id exactly, and give a concise non-empty reason.
""".strip()


class _FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class MediaStoryContext(_FrozenModel):
    """Minimal projection of finished copy, avoiding issue/rendering/rights coupling."""

    headline: str
    context: str
    temporal_context: str | None = None

    @field_validator("headline", "context")
    @classmethod
    def required_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("story context fields must not be empty")
        return value

    @classmethod
    def from_article_package(
        cls, package: ArticlePackage, *, temporal_context: str | None = None
    ) -> "MediaStoryContext":
        """Project only finished editorial copy needed for media correspondence."""
        parts = [package.dek, package.internet_read]
        parts.extend(f"{section.heading}: {section.body}" for section in package.sections)
        return cls(
            headline=package.headline,
            context="\n\n".join(part for part in parts if part.strip()),
            temporal_context=temporal_context,
        )


class MediaRelevanceStatus(StrEnum):
    PASS = "pass"
    HOLD = "hold"
    FAIL = "fail"


class MediaProvenanceStatus(StrEnum):
    AUTHORITATIVE = "authoritative"
    ATTRIBUTABLE_SECONDARY = "attributable_secondary"
    UNCLEAR = "unclear"
    PROBLEMATIC = "problematic"


class MediaTemporalStatus(StrEnum):
    CURRENT = "current"
    CONTEXTUAL = "contextual"
    MISMATCH = "mismatch"
    UNKNOWN = "unknown"


def media_is_eligible(
    relevance: MediaRelevanceStatus,
    provenance: MediaProvenanceStatus,
    temporal: MediaTemporalStatus = MediaTemporalStatus.UNKNOWN,
) -> bool:
    return relevance == MediaRelevanceStatus.PASS and provenance in {
        MediaProvenanceStatus.AUTHORITATIVE,
        MediaProvenanceStatus.ATTRIBUTABLE_SECONDARY,
    } and temporal != MediaTemporalStatus.MISMATCH


class MediaEligibilityAssessment(_FrozenModel):
    candidate_id: str
    relevance_status: MediaRelevanceStatus
    provenance_status: MediaProvenanceStatus
    temporal_status: MediaTemporalStatus
    reason: str
    eligible: bool

    @field_validator("candidate_id", "reason")
    @classmethod
    def required_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("assessment fields must not be empty")
        return value

    @model_validator(mode="after")
    def eligible_must_match_statuses(self) -> "MediaEligibilityAssessment":
        expected = media_is_eligible(
            self.relevance_status, self.provenance_status, self.temporal_status
        )
        if self.eligible is not expected:
            raise ValueError("eligible is inconsistent with eligibility statuses")
        return self


class MediaEligibilityBatch(_FrozenModel):
    results: tuple[MediaEligibilityAssessment, ...]
    requested_model: str
    actual_model: str
    response_id: str | None
    classified_at: datetime


class _ModelResults(_FrozenModel):
    results: tuple[MediaEligibilityAssessment, ...]


_RESPONSE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "candidate_id": {"type": "string", "minLength": 1},
                    "relevance_status": {"type": "string", "enum": [x.value for x in MediaRelevanceStatus]},
                    "provenance_status": {"type": "string", "enum": [x.value for x in MediaProvenanceStatus]},
                    "temporal_status": {"type": "string", "enum": [x.value for x in MediaTemporalStatus]},
                    "reason": {"type": "string", "minLength": 1},
                    "eligible": {"type": "boolean"},
                },
                "required": ["candidate_id", "relevance_status", "provenance_status", "temporal_status", "reason", "eligible"],
            },
        }
    },
    "required": ["results"],
}


def media_eligibility_contract_errors(
    candidates: tuple[MediaCandidate, ...], results: tuple[MediaEligibilityAssessment, ...]
) -> tuple[str, ...]:
    errors: list[str] = []
    if len(results) != len(candidates):
        errors.append(MEDIA_ELIGIBILITY_COUNT_MISMATCH)
    expected = tuple(media_candidate_id(candidate) for candidate in candidates)
    if tuple(result.candidate_id for result in results) != expected:
        errors.append(MEDIA_ELIGIBILITY_CANDIDATE_ORDER_MISMATCH)
    return tuple(errors)


def media_candidate_id(candidate: MediaCandidate) -> str:
    return f"{candidate.provider}:{candidate.provider_asset_id}"


def classify_media_eligibility(
    story: MediaStoryContext,
    candidates: tuple[MediaCandidate, ...],
    client: Any,
    model: str = DEFAULT_MEDIA_ELIGIBILITY_MODEL,
) -> MediaEligibilityBatch:
    candidate_ids = tuple(media_candidate_id(candidate) for candidate in candidates)
    if len(set(candidate_ids)) != len(candidate_ids):
        raise ValueError(DUPLICATE_MEDIA_CANDIDATE_ID)
    if not candidates:
        return MediaEligibilityBatch(results=(), requested_model=model, actual_model=model,
                                     response_id=None, classified_at=datetime.now(timezone.utc))

    model_input = {
        "story": story.model_dump(mode="json"),
        "candidates": [
            {
                "candidate_id": candidate_id,
                "provider": candidate.provider,
                "media_type": candidate.media_type,
                "title": candidate.title,
                "description": candidate.description,
                "published_at": candidate.published_at.isoformat() if candidate.published_at else None,
                "creator": candidate.creator,
                "source": candidate.source,
                "landing_url": candidate.landing_url,
            }
            for candidate_id, candidate in zip(candidate_ids, candidates)
        ],
    }
    response = client.responses.create(
        model=model,
        instructions=MEDIA_ELIGIBILITY_INSTRUCTIONS,
        input=json.dumps(model_input, ensure_ascii=False),
        store=False,
        text={"format": {"type": "json_schema", "name": "media_eligibility_results",
                         "strict": True, "schema": _RESPONSE_SCHEMA}},
    )
    output_text = getattr(response, "output_text", None)
    if not output_text:
        raise ValueError("media eligibility response has no output_text")
    parsed = _ModelResults.model_validate_json(output_text)
    errors = media_eligibility_contract_errors(candidates, parsed.results)
    if errors:
        raise ValueError(",".join(errors))
    return MediaEligibilityBatch(
        results=parsed.results,
        requested_model=model,
        actual_model=getattr(response, "model", None) or model,
        response_id=getattr(response, "id", None),
        classified_at=datetime.now(timezone.utc),
    )
