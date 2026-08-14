from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator, model_validator

from ksignal.engine.models import AccessStatus, StrEnum


class _FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class EvidenceLane(StrEnum):
    BEAUTY = "beauty"
    FOOD = "food"
    SOCIETY = "society"
    FANDOM = "fandom"
    SPORTS = "sports"


class TimestampStatus(StrEnum):
    RELIABLE = "reliable"
    AMBIGUOUS = "ambiguous"
    MISSING = "missing"


class IndependenceStatus(StrEnum):
    INDEPENDENT = "independent"
    DUPLICATE = "duplicate"
    SYNDICATED = "syndicated"
    UNCERTAIN = "uncertain"


class EvidenceDecision(StrEnum):
    PASS = "PASS"
    HOLD = "HOLD"
    FAIL = "FAIL"


class SearchContextRef(_FrozenModel):
    title: str
    source: str
    url: str


class EvidenceSubject(_FrozenModel):
    label: str
    aliases: tuple[str, ...] = ()


class EvidenceQuery(_FrozenModel):
    original: str
    normalized: str


class SearchWake(_FrozenModel):
    provider: Literal["google_trends_rss"]
    geo: Literal["KR"]
    observed_at: datetime
    approx_traffic_raw: str
    approx_traffic_floor: int = Field(ge=0)
    context_refs: tuple[SearchContextRef, ...] = ()

    @model_validator(mode="after")
    def validate_traffic_bucket(self) -> SearchWake:
        if not re.fullmatch(r"[\d,]+\+", self.approx_traffic_raw):
            raise ValueError("approx_traffic_raw must be digits/commas followed by '+'")
        digits = self.approx_traffic_raw[:-1].replace(",", "")
        if not digits or not digits.isdigit():
            raise ValueError("approx_traffic_raw has no deterministic numeric lower bound")
        if int(digits) != self.approx_traffic_floor:
            raise ValueError("approx_traffic_floor must match approx_traffic_raw")
        return self


class CollectionRun(_FrozenModel):
    run_id: str
    provider: str
    operation: str
    status: AccessStatus
    failure_mode: str | None = None
    started_at: datetime
    completed_at: datetime
    raw_item_count: int = Field(ge=0)
    relevant_item_count: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_item_counts(self) -> CollectionRun:
        if self.relevant_item_count > self.raw_item_count:
            raise ValueError("relevant_item_count cannot exceed raw_item_count")
        return self


class EvidenceRecord(_FrozenModel):
    evidence_id: str
    run_id: str
    provider: str
    medium: str
    provider_item_id: str | None = None
    source_name: str
    source_identity: str
    url: str
    title: str
    excerpt: str
    published_at: datetime | None = None
    published_at_raw: str | None = None
    first_seen_at: datetime
    timestamp_status: TimestampStatus
    temporal_eligible: bool
    duplicate_group_id: str
    independence_group_id: str
    independence_status: IndependenceStatus
    counts_toward_independence: bool

    @model_validator(mode="after")
    def validate_timestamp_and_independence(self) -> EvidenceRecord:
        if self.timestamp_status == TimestampStatus.RELIABLE:
            if self.published_at is None:
                raise ValueError("reliable timestamp requires published_at")
            if not self.temporal_eligible:
                raise ValueError("reliable timestamp requires temporal_eligible")
        elif self.temporal_eligible:
            raise ValueError("ambiguous or missing timestamp cannot be temporal_eligible")
        if (
            self.counts_toward_independence
            and self.independence_status != IndependenceStatus.INDEPENDENT
        ):
            raise ValueError("only independent evidence may count toward independence")
        return self


class DerivedCounts(_FrozenModel):
    evidence_count: int
    timestamped_evidence_count: int
    temporal_eligible_count: int
    independent_group_count: int
    provider_count: int
    media: tuple[str, ...]


class EvidencePacket(_FrozenModel):
    schema_version: Literal["evidence_packet.v0.1"]
    packet_id: str
    packet_revision: int = Field(ge=1)
    issue_id: str
    candidate_id: str
    lane: EvidenceLane
    subject: EvidenceSubject
    query: EvidenceQuery
    search_wake: SearchWake
    collection_runs: tuple[CollectionRun, ...] = Field(min_length=1)
    evidence: tuple[EvidenceRecord, ...]
    packet_created_at: datetime

    @model_validator(mode="before")
    @classmethod
    def discard_serialized_derived_counts(cls, data: Any) -> Any:
        if isinstance(data, Mapping) and "derived_counts" in data:
            data = dict(data)
            data.pop("derived_counts")
        return data

    @model_validator(mode="after")
    def validate_packet_links(self) -> EvidencePacket:
        run_ids = [run.run_id for run in self.collection_runs]
        if len(run_ids) != len(set(run_ids)):
            raise ValueError("run_id values must be unique")
        evidence_ids = [record.evidence_id for record in self.evidence]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("evidence_id values must be unique")
        runs = {run.run_id: run for run in self.collection_runs}
        for record in self.evidence:
            run = runs.get(record.run_id)
            if run is None:
                raise ValueError("evidence run_id must reference a collection run")
            if record.provider != run.provider:
                raise ValueError("evidence provider must match its collection run")
        return self

    @computed_field
    @property
    def derived_counts(self) -> DerivedCounts:
        independent_groups = {
            record.independence_group_id
            for record in self.evidence
            if record.counts_toward_independence
        }
        return DerivedCounts(
            evidence_count=len(self.evidence),
            timestamped_evidence_count=sum(
                record.published_at is not None for record in self.evidence
            ),
            temporal_eligible_count=sum(record.temporal_eligible for record in self.evidence),
            independent_group_count=len(independent_groups),
            provider_count=len({record.provider for record in self.evidence}),
            media=tuple(sorted({record.medium for record in self.evidence})),
        )


def structural_pass_blockers(packet: EvidencePacket) -> tuple[str, ...]:
    blockers: list[str] = []
    if packet.derived_counts.evidence_count == 0:
        blockers.append("NO_RELEVANT_DOWNSTREAM_EVIDENCE")
    if packet.derived_counts.independent_group_count < 2:
        blockers.append("INSUFFICIENT_INDEPENDENT_EVIDENCE")
    temporal_groups = {
        record.independence_group_id
        for record in packet.evidence
        if record.counts_toward_independence and record.temporal_eligible
    }
    if len(temporal_groups) < 2:
        blockers.append("INSUFFICIENT_TEMPORAL_EVIDENCE")
    return tuple(blockers)


class DimensionScore(_FrozenModel):
    score: int = Field(ge=0, le=10)
    evidence_ids: tuple[str, ...] = ()
    reason: str

    @field_validator("reason")
    @classmethod
    def reason_must_not_be_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("reason must not be empty")
        return value

    @field_validator("evidence_ids")
    @classmethod
    def evidence_ids_must_be_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("evidence_ids must be unique")
        return value


class EvidenceDimensions(_FrozenModel):
    evidence_sufficiency: DimensionScore
    independent_spread: DimensionScore
    temporal_coherence: DimensionScore
    search_content_alignment: DimensionScore
    emergence_stage: DimensionScore


class EvidenceAssessment(_FrozenModel):
    assessment_version: Literal["emergence_rubric.v0.1"]
    rubric_version: Literal["0.1"]
    packet_id: str
    packet_revision: int = Field(ge=1)
    decision: EvidenceDecision
    dimensions: EvidenceDimensions
    pass_blockers: tuple[str, ...] = ()
    supporting_evidence_ids: tuple[str, ...] = ()
    contradictions: tuple[str, ...] = ()
    unknowns: tuple[str, ...] = ()
    rationale: str
    assessed_at: datetime
    assessor_model: str

    @field_validator("rationale", "assessor_model")
    @classmethod
    def text_must_not_be_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be empty")
        return value

    @field_validator("supporting_evidence_ids")
    @classmethod
    def supporting_ids_must_be_unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("supporting_evidence_ids must be unique")
        return value


def assessment_contract_errors(
    packet: EvidencePacket,
    assessment: EvidenceAssessment,
) -> tuple[str, ...]:
    errors: list[str] = []
    if assessment.packet_id != packet.packet_id:
        errors.append("PACKET_ID_MISMATCH")
    if assessment.packet_revision != packet.packet_revision:
        errors.append("PACKET_REVISION_MISMATCH")

    packet_evidence_ids = {record.evidence_id for record in packet.evidence}
    dimension_names = (
        "evidence_sufficiency",
        "independent_spread",
        "temporal_coherence",
        "search_content_alignment",
        "emergence_stage",
    )
    for dimension_name in dimension_names:
        dimension = getattr(assessment.dimensions, dimension_name)
        for evidence_id in dimension.evidence_ids:
            if evidence_id not in packet_evidence_ids:
                errors.append(f"UNKNOWN_EVIDENCE_ID:{dimension_name}:{evidence_id}")
    for evidence_id in assessment.supporting_evidence_ids:
        if evidence_id not in packet_evidence_ids:
            errors.append(f"UNKNOWN_SUPPORTING_EVIDENCE_ID:{evidence_id}")

    if assessment.decision == EvidenceDecision.PASS:
        for blocker in structural_pass_blockers(packet):
            errors.append(f"PASS_STRUCTURAL_BLOCKER:{blocker}")
        if assessment.pass_blockers:
            errors.append("PASS_BLOCKERS_MUST_BE_EMPTY")
        for dimension_name in dimension_names:
            if getattr(assessment.dimensions, dimension_name).score < 6:
                errors.append(f"PASS_DIMENSION_BELOW_MINIMUM:{dimension_name}")
    return tuple(errors)
