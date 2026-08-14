from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator

from ksignal.engine.models import StrEnum
from ksignal.engine.source_collectors import GoogleWakeCandidate


DEFAULT_RELEVANCE_CLASSIFIER_MODEL = "gpt-5-mini"

DUPLICATE_RELEVANCE_CANDIDATE_ID = "DUPLICATE_RELEVANCE_CANDIDATE_ID"
RELEVANCE_COUNT_MISMATCH = "RELEVANCE_COUNT_MISMATCH"
RELEVANCE_CANDIDATE_ORDER_MISMATCH = "RELEVANCE_CANDIDATE_ORDER_MISMATCH"

RELEVANCE_CLASSIFIER_INSTRUCTIONS = """
You are a constrained K-Signal candidate relevance classifier. Answer relevance only:
does each supplied candidate materially concern the same subject, event, or development
represented by the single supplied Google wake? Use only the supplied wake and candidate
metadata. Do not browse, call tools, or use outside knowledge, and do not invent missing
facts or chronology.

The same subject is not sufficient for relevance. The same setting is not sufficient
either: a candidate may concern the same person, organization, team, sport, or even the
same game while materially concerning another development. A subject merely listed,
tagged, or incidentally mentioned is not relevant. Set relevant=true only when the
candidate metadata materially concerns the same represented event or development.

Identical wording is not required. Aliases, shortened names, translations, paraphrases,
event references, follow-up language, recovery language, and well-wishes language can be
relevant when the supplied metadata materially ties them to the represented development.
A candidate may include surrounding material when that development remains a material
part of the item.

Provider or source identity does not determine relevance. matched_subject identifies the
apparent matching subject in the candidate, but matched_subject is not proof of relevance
and may name the wake subject when relevant=false. Chronology may assist when supplied,
but recency alone is not proof of relevance. Do not make emergence, propagation,
independence, duplication, syndication, EvidencePacket inclusion, PASS/HOLD/FAIL,
publication, or editorial judgments.

When the wake has no context and its query is entity-only or subject-only, do not invent
a missing development. Same-subject coverage alone must be relevant=false with low
confidence because the wake does not establish which development caused it. Absence of
context is not a universal negative: an event-enriched query can itself supply the
missing event or development context, and candidates can then be judged normally.
Whether a query is entity-only or event-enriched is a semantic judgment; do not rely on
word counts, keyword tables, name detection, or other mechanical heuristics.

Confidence is relevance-certainty audit metadata only: high means the relevance or
non-relevance judgment is clearly supported by supplied metadata; medium means it is
reasonably supported with meaningful ambiguity; low means supplied metadata is too thin
or ambiguous for a strong judgment. Confidence must not filter candidates or change the
relevant value. Return exactly one result per candidate in the original order, reproduce
each candidate_id exactly, and give a concise non-empty reason grounded only in supplied
metadata.
""".strip()


class _FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class RelevanceProvider(StrEnum):
    NEWSIS = "newsis"
    YOUTUBE = "youtube"


class RelevanceConfidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class RelevanceCandidate(_FrozenModel):
    candidate_id: str
    provider: RelevanceProvider
    source: str
    title: str
    description: str
    published_at_raw: str

    @field_validator("candidate_id")
    @classmethod
    def candidate_id_must_not_be_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("candidate_id must not be empty")
        return value


class CandidateRelevance(_FrozenModel):
    candidate_id: str
    relevant: bool
    confidence: RelevanceConfidence
    matched_subject: str
    reason: str

    @field_validator("candidate_id", "reason")
    @classmethod
    def field_must_not_be_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("field must not be empty")
        return value


class CandidateRelevanceBatch(_FrozenModel):
    results: tuple[CandidateRelevance, ...]
    requested_model: str
    actual_model: str
    response_id: str | None
    classified_at: datetime


class _ModelResults(_FrozenModel):
    results: tuple[CandidateRelevance, ...]


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
                    "relevant": {"type": "boolean"},
                    "confidence": {
                        "type": "string",
                        "enum": [confidence.value for confidence in RelevanceConfidence],
                    },
                    "matched_subject": {"type": "string"},
                    "reason": {"type": "string", "minLength": 1},
                },
                "required": [
                    "candidate_id",
                    "relevant",
                    "confidence",
                    "matched_subject",
                    "reason",
                ],
            },
        }
    },
    "required": ["results"],
}


def relevance_contract_errors(
    candidates: tuple[RelevanceCandidate, ...],
    results: tuple[CandidateRelevance, ...],
) -> tuple[str, ...]:
    errors: list[str] = []
    if len(results) != len(candidates):
        errors.append(RELEVANCE_COUNT_MISMATCH)
    if tuple(result.candidate_id for result in results) != tuple(
        candidate.candidate_id for candidate in candidates
    ):
        errors.append(RELEVANCE_CANDIDATE_ORDER_MISMATCH)
    return tuple(errors)


def classify_candidate_relevance(
    wake: GoogleWakeCandidate,
    candidates: tuple[RelevanceCandidate, ...],
    client: Any,
    model: str = DEFAULT_RELEVANCE_CLASSIFIER_MODEL,
) -> CandidateRelevanceBatch:
    candidate_ids = tuple(candidate.candidate_id for candidate in candidates)
    if len(set(candidate_ids)) != len(candidate_ids):
        raise ValueError(DUPLICATE_RELEVANCE_CANDIDATE_ID)

    if not candidates:
        return CandidateRelevanceBatch(
            results=(),
            requested_model=model,
            actual_model=model,
            response_id=None,
            classified_at=datetime.now(timezone.utc),
        )

    model_input = {
        "wake": {
            "query": wake.query,
            "context": [
                {"title": context.title, "source": context.source}
                for context in wake.context_refs
            ],
        },
        "candidates": [
            {
                "candidate_id": candidate.candidate_id,
                "provider": candidate.provider.value,
                "source": candidate.source,
                "title": candidate.title,
                "description": candidate.description,
                "published_at_raw": candidate.published_at_raw,
            }
            for candidate in candidates
        ],
    }
    response = client.responses.create(
        model=model,
        instructions=RELEVANCE_CLASSIFIER_INSTRUCTIONS,
        input=json.dumps(model_input, ensure_ascii=False),
        store=False,
        text={
            "format": {
                "type": "json_schema",
                "name": "candidate_relevance_results",
                "strict": True,
                "schema": _RESPONSE_SCHEMA,
            }
        },
    )
    output_text = getattr(response, "output_text", None)
    if not output_text:
        raise ValueError("relevance classifier response has no output_text")
    parsed = _ModelResults.model_validate_json(output_text)
    errors = relevance_contract_errors(candidates, parsed.results)
    if errors:
        raise ValueError(",".join(errors))
    classified_at = datetime.now(timezone.utc)

    return CandidateRelevanceBatch(
        results=parsed.results,
        requested_model=model,
        actual_model=getattr(response, "model", None) or model,
        response_id=getattr(response, "id", None),
        classified_at=classified_at,
    )
