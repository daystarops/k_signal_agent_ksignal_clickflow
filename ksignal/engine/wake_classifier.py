from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator

from ksignal.engine.models import StrEnum
from ksignal.engine.source_collectors import GoogleWakeCandidate


DEFAULT_LANE_CLASSIFIER_MODEL = "gpt-5-mini"

LANE_CLASSIFIER_INSTRUCTIONS = """
You are a constrained K-Signal wake lane classifier. Your only task is to assign one
lane to each supplied Google Trends KR wake, using only its query and supplied Google
metadata. Do not browse, call tools, or use outside knowledge.

Classify WHY THE QUERY IS WAKING NOW. Current-development context outranks permanent
entity identity, profession, industry, product category, or usual public identity. A
recognizable entity name does not automatically establish a lane, and you must not
infer a profession from a bare name when the supplied context does not establish it.

Use exactly one of these lanes:
- beauty: cosmetics, skincare, hair, nails, aesthetic beauty treatments, beauty
  products, looks, or culture; not general fashion, magazines, clothing, or lifestyle.
- food: food, dining, restaurants, beverages, cooking, food products, or food-related
  consumer culture.
- society: government, municipalities, law, courts, criminal proceedings, law
  enforcement, public safety, labor, economy, public finance, education, community
  affairs, social issues, public policy, enforcement, or major public-interest events.
- fandom: music artists, idols, actors, television, film, entertainment personalities,
  creators, webtoons as creator/entertainment culture, celebrity discourse, fandom
  behavior, or entertainment-oriented internet culture. Do not use fandom merely for
  entertainment-industry identity when the current event is a society-domain event.
- sports: athletes in sports context, teams, leagues, matches, competitions, sports
  organizations, injuries, or incidents. Do not use sports merely for a sports identity
  when current context establishes a court, criminal, government, or public-affairs event.
- out_of_scope: no reasonable supplied connection to the five K-Signal lanes, including
  ordinary retail promotions, generic loyalty discounts, unrelated weather, consumer
  commerce, or otherwise unrelated topics.

Use a sensitive radar: when supplied metadata gives a reasonable in-scope interpretation,
choose the best in-scope lane even at low confidence. Low confidence does not mean
out_of_scope, and you must not force every wake in scope.

Confidence is audit metadata only: high means the supplied query/context clearly
establishes the current-development lane; medium means the best lane is reasonably
supported with ambiguity; low means an in-scope lane is plausible but weakly supported.
Confidence must not discard a wake, control collection, act as a score, or decide any
outcome. A broad query can have high confidence when multiple context references converge.

approx_traffic_raw is magnitude only. It must not determine lane, confidence, importance,
emergence, growth, velocity, or acceleration. Give a concise, non-empty reason grounded
only in supplied metadata. Make no relevance, evidence, independence, emergence,
PASS/HOLD/FAIL, publication, or editorial judgment. Return one result per wake in the
original order and reproduce every query exactly.
""".strip()


class _FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class WakeLane(StrEnum):
    BEAUTY = "beauty"
    FOOD = "food"
    SOCIETY = "society"
    FANDOM = "fandom"
    SPORTS = "sports"
    OUT_OF_SCOPE = "out_of_scope"


class LaneConfidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class WakeLaneClassification(_FrozenModel):
    query: str
    lane: WakeLane
    confidence: LaneConfidence
    reason: str

    @field_validator("reason")
    @classmethod
    def reason_must_not_be_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("reason must not be empty")
        return value


class WakeLaneClassificationBatch(_FrozenModel):
    classifications: tuple[WakeLaneClassification, ...]
    requested_model: str
    actual_model: str
    response_id: str | None
    classified_at: datetime


class _ModelResults(_FrozenModel):
    results: tuple[WakeLaneClassification, ...]


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
                    "query": {"type": "string"},
                    "lane": {"type": "string", "enum": [lane.value for lane in WakeLane]},
                    "confidence": {
                        "type": "string",
                        "enum": [confidence.value for confidence in LaneConfidence],
                    },
                    "reason": {"type": "string", "minLength": 1},
                },
                "required": ["query", "lane", "confidence", "reason"],
            },
        }
    },
    "required": ["results"],
}


def lane_classification_contract_errors(
    wakes: tuple[GoogleWakeCandidate, ...],
    classifications: tuple[WakeLaneClassification, ...],
) -> tuple[str, ...]:
    errors: list[str] = []
    if len(classifications) != len(wakes):
        errors.append("CLASSIFICATION_COUNT_MISMATCH")
    if tuple(item.query for item in classifications) != tuple(wake.query for wake in wakes):
        errors.append("CLASSIFICATION_QUERY_ORDER_MISMATCH")
    return tuple(errors)


def classify_wake_lanes(
    wakes: tuple[GoogleWakeCandidate, ...],
    client: Any,
    model: str = DEFAULT_LANE_CLASSIFIER_MODEL,
) -> WakeLaneClassificationBatch:
    if not wakes:
        classified_at = datetime.now(timezone.utc)
        return WakeLaneClassificationBatch(
            classifications=(),
            requested_model=model,
            actual_model=model,
            response_id=None,
            classified_at=classified_at,
        )

    model_input = [
        {
            "query": wake.query,
            "approx_traffic_raw": wake.approx_traffic_raw,
            "context": [
                {"title": context.title, "source": context.source}
                for context in wake.context_refs
            ],
        }
        for wake in wakes
    ]
    response = client.responses.create(
        model=model,
        instructions=LANE_CLASSIFIER_INSTRUCTIONS,
        input=json.dumps(model_input, ensure_ascii=False),
        store=False,
        text={
            "format": {
                "type": "json_schema",
                "name": "wake_lane_classifications",
                "strict": True,
                "schema": _RESPONSE_SCHEMA,
            }
        },
    )
    output_text = getattr(response, "output_text", None)
    if not output_text:
        raise ValueError("lane classifier response has no output_text")
    parsed = _ModelResults.model_validate_json(output_text)
    errors = lane_classification_contract_errors(wakes, parsed.results)
    if errors:
        raise ValueError(",".join(errors))
    classified_at = datetime.now(timezone.utc)

    return WakeLaneClassificationBatch(
        classifications=parsed.results,
        requested_model=model,
        actual_model=getattr(response, "model", None) or model,
        response_id=getattr(response, "id", None),
        classified_at=classified_at,
    )
