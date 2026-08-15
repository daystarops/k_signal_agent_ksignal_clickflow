from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from ksignal.engine.evidence_record_bridge import (
    NewsisEvidenceSource,
    YouTubeEvidenceSource,
)
from ksignal.engine.independence_classifier import IndependenceCandidate
from ksignal.engine.newsis_candidate_narrowing import NewsisNarrowedCandidate
from ksignal.engine.relevance_classifier import RelevanceCandidate, RelevanceProvider
from ksignal.engine.source_collectors import NewsisCollection, YouTubeCollection


DUPLICATE_NEWSIS_BINDING_CANDIDATE_ID = "DUPLICATE_NEWSIS_BINDING_CANDIDATE_ID"
DUPLICATE_NEWSIS_BINDING_URL = "DUPLICATE_NEWSIS_BINDING_URL"
NEWSIS_SOURCE_URL_NOT_FOUND = "NEWSIS_SOURCE_URL_NOT_FOUND"
NEWSIS_SOURCE_URL_AMBIGUOUS = "NEWSIS_SOURCE_URL_AMBIGUOUS"
DUPLICATE_YOUTUBE_CANDIDATE_ID = "DUPLICATE_YOUTUBE_CANDIDATE_ID"


class _FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class NewsisCandidateBinding(_FrozenModel):
    candidate_id: str
    narrowed: NewsisNarrowedCandidate

    @field_validator("candidate_id")
    @classmethod
    def candidate_id_must_not_be_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("candidate_id must not be empty")
        return value


class PreparedCandidate(_FrozenModel):
    source: NewsisEvidenceSource | YouTubeEvidenceSource
    independence_candidate: IndependenceCandidate

    @model_validator(mode="after")
    def validate_correlation(self) -> PreparedCandidate:
        if self.source.candidate.candidate_id != self.independence_candidate.candidate_id:
            raise ValueError("source and independence candidate IDs must match")
        if self.source.candidate.provider != self.independence_candidate.provider:
            raise ValueError("source and independence candidate providers must match")
        return self


def _require_unique(values: Sequence[object], error: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(error)


def prepare_newsis_candidates(
    *,
    bindings: Sequence[NewsisCandidateBinding],
    collection: NewsisCollection,
) -> tuple[PreparedCandidate, ...]:
    binding_ids = tuple(binding.candidate_id for binding in bindings)
    binding_urls = tuple(binding.narrowed.url for binding in bindings)
    _require_unique(binding_ids, DUPLICATE_NEWSIS_BINDING_CANDIDATE_ID)
    _require_unique(binding_urls, DUPLICATE_NEWSIS_BINDING_URL)

    prepared: list[PreparedCandidate] = []
    for binding in bindings:
        matches = tuple(item for item in collection.items if item.url == binding.narrowed.url)
        if not matches:
            raise ValueError(NEWSIS_SOURCE_URL_NOT_FOUND)
        if len(matches) > 1:
            raise ValueError(NEWSIS_SOURCE_URL_AMBIGUOUS)
        item = matches[0]
        relevance_candidate = RelevanceCandidate(
            candidate_id=binding.candidate_id,
            provider=RelevanceProvider.NEWSIS,
            source="뉴시스",
            title=item.title,
            description=item.description,
            published_at_raw=item.published_at_raw,
        )
        prepared.append(
            PreparedCandidate(
                source=NewsisEvidenceSource(candidate=relevance_candidate, item=item),
                independence_candidate=IndependenceCandidate(
                    candidate_id=binding.candidate_id,
                    provider=RelevanceProvider.NEWSIS,
                    source_name="뉴시스",
                    source_identity="newsis:publisher",
                    provider_item_id=None,
                    url=item.url,
                    title=item.title,
                    description=item.description,
                ),
            )
        )
    return tuple(prepared)


def prepare_youtube_candidates(
    *, collection: YouTubeCollection
) -> tuple[PreparedCandidate, ...]:
    candidate_ids = tuple(f"youtube:{item.video_id}" for item in collection.items)
    _require_unique(candidate_ids, DUPLICATE_YOUTUBE_CANDIDATE_ID)

    prepared: list[PreparedCandidate] = []
    for item, candidate_id in zip(collection.items, candidate_ids):
        relevance_candidate = RelevanceCandidate(
            candidate_id=candidate_id,
            provider=RelevanceProvider.YOUTUBE,
            source=item.channel_title,
            title=item.title,
            description=item.description,
            published_at_raw=item.published_at_raw,
        )
        prepared.append(
            PreparedCandidate(
                source=YouTubeEvidenceSource(candidate=relevance_candidate, item=item),
                independence_candidate=IndependenceCandidate(
                    candidate_id=candidate_id,
                    provider=RelevanceProvider.YOUTUBE,
                    source_name=item.channel_title,
                    source_identity=item.channel_id,
                    provider_item_id=item.video_id,
                    url=item.url,
                    title=item.title,
                    description=item.description,
                ),
            )
        )
    return tuple(prepared)
