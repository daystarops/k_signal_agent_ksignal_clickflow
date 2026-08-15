from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from ksignal.engine.evidence import IndependenceStatus
from ksignal.engine.relevance_classifier import RelevanceProvider


DEFAULT_INDEPENDENCE_CLASSIFIER_MODEL = "gpt-5-mini"

DUPLICATE_INDEPENDENCE_CANDIDATE_ID = "DUPLICATE_INDEPENDENCE_CANDIDATE_ID"
INDEPENDENCE_COUNT_MISMATCH = "INDEPENDENCE_COUNT_MISMATCH"
INDEPENDENCE_CANDIDATE_ORDER_MISMATCH = "INDEPENDENCE_CANDIDATE_ORDER_MISMATCH"

INDEPENDENCE_CLASSIFIER_INSTRUCTIONS = """
You are a constrained K-Signal provenance classifier.

Judge ONLY whether each supplied YouTube item has enough explicit metadata to establish
an independent content origin. Use only the supplied candidate_id, channel_id,
channel_title, title, and description. Do not browse or use outside knowledge. Do not
infer provenance from popularity, branding, channel name, subscriber assumptions,
professional appearance, or source diversity. A different YouTube channel is NOT
evidence of independence.

Return exactly one of:

INDEPENDENT: The supplied metadata affirmatively establishes that this channel itself
produced original reporting, commentary, analysis, interviewing, recording, or other
original treatment of the development. Explicit evidence is required. Do not infer
original authorship merely because the item is framed as a review, reaction, recap,
discussion, or well-wish.

SYNDICATED: The supplied metadata affirmatively attributes the footage, source material,
copyright ownership, or underlying content to an external source or owner, indicating
redistribution, reposting, syndication, or reuse rather than an independently established
origin.

UNCERTAIN: The metadata does not explicitly establish either independent origin or
external redistribution. When provenance is uncertain, under-count it. Do not upgrade
uncertainty to independence.

Do not decide relevance, duplication, source grouping, emergence, propagation,
EvidencePacket inclusion, or PASS/HOLD/FAIL. Return results in exactly the supplied
candidate order. Give a concise reason grounded only in supplied metadata.
""".strip()


class _FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class IndependenceCandidate(_FrozenModel):
    candidate_id: str
    provider: RelevanceProvider
    source_name: str
    source_identity: str
    provider_item_id: str | None
    url: str
    title: str
    description: str

    @field_validator("candidate_id", "source_name", "source_identity", "url")
    @classmethod
    def required_text_must_not_be_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("field must not be empty")
        return value


class IndependenceAssignment(_FrozenModel):
    candidate_id: str
    duplicate_group_id: str
    independence_group_id: str
    independence_status: IndependenceStatus
    counts_toward_independence: bool
    reason: str

    @field_validator(
        "candidate_id", "duplicate_group_id", "independence_group_id", "reason"
    )
    @classmethod
    def text_must_not_be_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("field must not be empty")
        return value

    @model_validator(mode="after")
    def validate_countability(self) -> IndependenceAssignment:
        should_count = self.independence_status == IndependenceStatus.INDEPENDENT
        if self.counts_toward_independence != should_count:
            raise ValueError(
                "counts_toward_independence must be true exactly when "
                "independence_status is independent"
            )
        return self


class IndependenceBatch(_FrozenModel):
    results: tuple[IndependenceAssignment, ...]
    requested_model: str
    actual_model: str | None
    response_id: str | None
    classified_at: datetime


class _ModelResult(_FrozenModel):
    candidate_id: str
    status: Literal["independent", "syndicated", "uncertain"]
    reason: str

    @field_validator("candidate_id", "reason")
    @classmethod
    def text_must_not_be_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("field must not be empty")
        return value


class _ModelResults(_FrozenModel):
    results: tuple[_ModelResult, ...]


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
                    "status": {
                        "type": "string",
                        "enum": ["independent", "syndicated", "uncertain"],
                    },
                    "reason": {"type": "string", "minLength": 1},
                },
                "required": ["candidate_id", "status", "reason"],
            },
        }
    },
    "required": ["results"],
}


def _duplicate_components(
    candidates: tuple[IndependenceCandidate, ...],
) -> tuple[int, ...]:
    parents = list(range(len(candidates)))

    def find(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    def union(left: int, right: int) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            earlier, later = sorted((left_root, right_root))
            parents[later] = earlier

    item_ids: dict[tuple[RelevanceProvider, str], int] = {}
    urls: dict[str, int] = {}
    for index, candidate in enumerate(candidates):
        if candidate.provider_item_id:
            key = (candidate.provider, candidate.provider_item_id)
            if key in item_ids:
                union(index, item_ids[key])
            else:
                item_ids[key] = index
        if candidate.url in urls:
            union(index, urls[candidate.url])
        else:
            urls[candidate.url] = index
    return tuple(find(index) for index in range(len(candidates)))


def _independence_group(candidate: IndependenceCandidate) -> str:
    if candidate.provider == RelevanceProvider.NEWSIS:
        return "newsis:publisher"
    return f"youtube:channel:{candidate.source_identity}"


def classify_candidate_independence(
    *,
    candidates: Sequence[IndependenceCandidate],
    client: Any,
    model: str = DEFAULT_INDEPENDENCE_CLASSIFIER_MODEL,
) -> IndependenceBatch:
    supplied = tuple(candidates)
    candidate_ids = tuple(candidate.candidate_id for candidate in supplied)
    if len(set(candidate_ids)) != len(candidate_ids):
        raise ValueError(DUPLICATE_INDEPENDENCE_CANDIDATE_ID)

    canonical_indexes = _duplicate_components(supplied)
    youtube_indexes = tuple(
        index
        for index, candidate in enumerate(supplied)
        if canonical_indexes[index] == index
        and candidate.provider == RelevanceProvider.YOUTUBE
    )

    response = None
    model_results: tuple[_ModelResult, ...] = ()
    if youtube_indexes:
        model_input = {
            "candidates": [
                {
                    "candidate_id": supplied[index].candidate_id,
                    "channel_id": supplied[index].source_identity,
                    "channel_title": supplied[index].source_name,
                    "title": supplied[index].title,
                    "description": supplied[index].description,
                }
                for index in youtube_indexes
            ]
        }
        response = client.responses.create(
            model=model,
            instructions=INDEPENDENCE_CLASSIFIER_INSTRUCTIONS,
            input=json.dumps(model_input, ensure_ascii=False),
            store=False,
            text={
                "format": {
                    "type": "json_schema",
                    "name": "youtube_independence_results",
                    "strict": True,
                    "schema": _RESPONSE_SCHEMA,
                }
            },
        )
        output_text = getattr(response, "output_text", None)
        if not output_text:
            raise ValueError("independence classifier response has no output_text")
        model_results = _ModelResults.model_validate_json(output_text).results
        if len(model_results) != len(youtube_indexes):
            raise ValueError(INDEPENDENCE_COUNT_MISMATCH)
        expected_ids = tuple(supplied[index].candidate_id for index in youtube_indexes)
        if tuple(result.candidate_id for result in model_results) != expected_ids:
            raise ValueError(INDEPENDENCE_CANDIDATE_ORDER_MISMATCH)

    provenance_by_index = dict(zip(youtube_indexes, model_results, strict=True))
    assignments: list[IndependenceAssignment] = []
    for index, candidate in enumerate(supplied):
        canonical_index = canonical_indexes[index]
        canonical = supplied[canonical_index]
        duplicate_group_id = f"duplicate:{canonical.candidate_id}"
        independence_group_id = _independence_group(canonical)
        if index != canonical_index:
            status = IndependenceStatus.DUPLICATE
            counts = False
            reason = f"Exact duplicate of canonical candidate {canonical.candidate_id}."
        elif candidate.provider == RelevanceProvider.NEWSIS:
            status = IndependenceStatus.INDEPENDENT
            counts = True
            reason = (
                "Relevant record is attributable to Newsis; Newsis forms one publisher "
                "independence group."
            )
        else:
            model_result = provenance_by_index[index]
            status = IndependenceStatus(model_result.status)
            counts = status == IndependenceStatus.INDEPENDENT
            reason = model_result.reason
        assignments.append(
            IndependenceAssignment(
                candidate_id=candidate.candidate_id,
                duplicate_group_id=duplicate_group_id,
                independence_group_id=independence_group_id,
                independence_status=status,
                counts_toward_independence=counts,
                reason=reason,
            )
        )

    completed_results = tuple(assignments)
    classified_at = datetime.now(timezone.utc)
    return IndependenceBatch(
        results=completed_results,
        requested_model=model,
        actual_model=getattr(response, "model", None) if response is not None else None,
        response_id=getattr(response, "id", None) if response is not None else None,
        classified_at=classified_at,
    )
