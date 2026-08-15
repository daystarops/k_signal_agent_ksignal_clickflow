from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from ksignal.engine.evidence import EvidenceRecord, TimestampStatus
from ksignal.engine.independence_classifier import IndependenceAssignment
from ksignal.engine.relevance_classifier import (
    CandidateRelevance,
    RelevanceCandidate,
    RelevanceProvider,
)
from ksignal.engine.source_collectors import NewsisItem, YouTubeItem


DUPLICATE_BRIDGE_SOURCE_CANDIDATE_ID = "DUPLICATE_BRIDGE_SOURCE_CANDIDATE_ID"
DUPLICATE_BRIDGE_RELEVANCE_CANDIDATE_ID = "DUPLICATE_BRIDGE_RELEVANCE_CANDIDATE_ID"
DUPLICATE_BRIDGE_INDEPENDENCE_CANDIDATE_ID = "DUPLICATE_BRIDGE_INDEPENDENCE_CANDIDATE_ID"
DUPLICATE_BRIDGE_COLLECTION_PROVIDER = "DUPLICATE_BRIDGE_COLLECTION_PROVIDER"
BRIDGE_RELEVANCE_COUNT_MISMATCH = "BRIDGE_RELEVANCE_COUNT_MISMATCH"
BRIDGE_RELEVANCE_CANDIDATE_ORDER_MISMATCH = "BRIDGE_RELEVANCE_CANDIDATE_ORDER_MISMATCH"
BRIDGE_INDEPENDENCE_COUNT_MISMATCH = "BRIDGE_INDEPENDENCE_COUNT_MISMATCH"
BRIDGE_INDEPENDENCE_CANDIDATE_ORDER_MISMATCH = "BRIDGE_INDEPENDENCE_CANDIDATE_ORDER_MISMATCH"
BRIDGE_COLLECTION_CONTEXT_MISMATCH = "BRIDGE_COLLECTION_CONTEXT_MISMATCH"


class _FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class NewsisEvidenceSource(_FrozenModel):
    candidate: RelevanceCandidate
    item: NewsisItem

    @model_validator(mode="after")
    def validate_correlation(self) -> NewsisEvidenceSource:
        if self.candidate.provider != RelevanceProvider.NEWSIS:
            raise ValueError("candidate provider must be newsis")
        if self.candidate.source != "뉴시스":
            raise ValueError("candidate source must be 뉴시스")
        for field in ("title", "description", "published_at_raw"):
            if getattr(self.candidate, field) != getattr(self.item, field):
                raise ValueError(f"candidate {field} must match Newsis item")
        return self


class YouTubeEvidenceSource(_FrozenModel):
    candidate: RelevanceCandidate
    item: YouTubeItem

    @model_validator(mode="after")
    def validate_correlation(self) -> YouTubeEvidenceSource:
        if self.candidate.provider != RelevanceProvider.YOUTUBE:
            raise ValueError("candidate provider must be youtube")
        if self.candidate.candidate_id != f"youtube:{self.item.video_id}":
            raise ValueError("candidate_id must equal youtube:<video_id>")
        if self.candidate.source != self.item.channel_title:
            raise ValueError("candidate source must match channel_title")
        for field in ("title", "description", "published_at_raw"):
            if getattr(self.candidate, field) != getattr(self.item, field):
                raise ValueError(f"candidate {field} must match YouTube item")
        return self


class EvidenceCollectionContext(_FrozenModel):
    provider: RelevanceProvider
    run_id: str
    completed_at: datetime

    @field_validator("run_id")
    @classmethod
    def run_id_must_not_be_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("run_id must not be empty")
        return value

    @field_validator("completed_at")
    @classmethod
    def completed_at_must_be_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("completed_at must be timezone-aware")
        return value


EvidenceSource = NewsisEvidenceSource | YouTubeEvidenceSource


def _require_unique(values: Sequence[object], error: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(error)


def build_evidence_records(
    *,
    sources: Sequence[NewsisEvidenceSource | YouTubeEvidenceSource],
    relevance_results: Sequence[CandidateRelevance],
    independence_assignments: Sequence[IndependenceAssignment],
    collection_contexts: Sequence[EvidenceCollectionContext],
) -> tuple[EvidenceRecord, ...]:
    source_ids = tuple(source.candidate.candidate_id for source in sources)
    relevance_ids = tuple(result.candidate_id for result in relevance_results)
    independence_ids = tuple(
        assignment.candidate_id for assignment in independence_assignments
    )
    context_providers = tuple(context.provider for context in collection_contexts)

    _require_unique(source_ids, DUPLICATE_BRIDGE_SOURCE_CANDIDATE_ID)
    _require_unique(relevance_ids, DUPLICATE_BRIDGE_RELEVANCE_CANDIDATE_ID)
    _require_unique(independence_ids, DUPLICATE_BRIDGE_INDEPENDENCE_CANDIDATE_ID)
    _require_unique(context_providers, DUPLICATE_BRIDGE_COLLECTION_PROVIDER)

    if len(relevance_ids) != len(source_ids):
        raise ValueError(BRIDGE_RELEVANCE_COUNT_MISMATCH)
    if relevance_ids != source_ids:
        raise ValueError(BRIDGE_RELEVANCE_CANDIDATE_ORDER_MISMATCH)

    relevant_ids = tuple(
        result.candidate_id for result in relevance_results if result.relevant
    )
    if len(independence_ids) != len(relevant_ids):
        raise ValueError(BRIDGE_INDEPENDENCE_COUNT_MISMATCH)
    if independence_ids != relevant_ids:
        raise ValueError(BRIDGE_INDEPENDENCE_CANDIDATE_ORDER_MISMATCH)

    source_providers = {source.candidate.provider for source in sources}
    if set(context_providers) != source_providers:
        raise ValueError(BRIDGE_COLLECTION_CONTEXT_MISMATCH)

    contexts = {context.provider: context for context in collection_contexts}
    assignments = iter(independence_assignments)
    records: list[EvidenceRecord] = []
    for source, relevance in zip(sources, relevance_results, strict=True):
        if not relevance.relevant:
            continue
        assignment = next(assignments)
        context = contexts[source.candidate.provider]
        if isinstance(source, NewsisEvidenceSource):
            item = source.item
            if item.published_at is not None:
                timestamp_status = TimestampStatus.RELIABLE
                temporal_eligible = True
            elif item.published_at_raw.strip():
                timestamp_status = TimestampStatus.AMBIGUOUS
                temporal_eligible = False
            else:
                timestamp_status = TimestampStatus.MISSING
                temporal_eligible = False
            provider_item_id = None
            provider = "newsis"
            medium = "news"
            source_name = "뉴시스"
            source_identity = "newsis:publisher"
        else:
            item = source.item
            timestamp_status = TimestampStatus.RELIABLE
            temporal_eligible = True
            provider_item_id = item.video_id
            provider = "youtube"
            medium = "video"
            source_name = item.channel_title
            source_identity = item.channel_id

        records.append(
            EvidenceRecord(
                evidence_id=source.candidate.candidate_id,
                run_id=context.run_id,
                provider=provider,
                medium=medium,
                provider_item_id=provider_item_id,
                source_name=source_name,
                source_identity=source_identity,
                url=item.url,
                title=item.title,
                excerpt=item.description,
                published_at=item.published_at,
                published_at_raw=item.published_at_raw,
                first_seen_at=context.completed_at,
                timestamp_status=timestamp_status,
                temporal_eligible=temporal_eligible,
                duplicate_group_id=assignment.duplicate_group_id,
                independence_group_id=assignment.independence_group_id,
                independence_status=assignment.independence_status,
                counts_toward_independence=assignment.counts_toward_independence,
            )
        )
    return tuple(records)
