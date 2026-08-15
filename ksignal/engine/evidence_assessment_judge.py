from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from ksignal.engine.evidence import (
    EvidenceAssessment,
    EvidenceDecision,
    EvidenceDimensions,
    EvidencePacket,
    assessment_contract_errors,
    structural_pass_blockers,
)


EVIDENCE_JUDGE_RESPONSE_NOT_COMPLETED = "evidence judge response not completed"
EVIDENCE_JUDGE_EMPTY_OUTPUT = "evidence judge response has no output_text"

EVIDENCE_ASSESSMENT_JUDGE_INSTRUCTIONS = """
You are K-Signal's evidence judge.

Your only question is:

Does this EvidencePacket support the conclusion that attention around
this topic is emerging and propagating?

Judge ONLY from the supplied packet.

Do not use outside knowledge.
Do not browse.
Do not infer missing provenance.
Do not convert inference into observation.
Do not write publication copy.

The supplied structural_pass_blockers are deterministic and authoritative.

If structural_pass_blockers is non-empty:
- decision MUST NOT be PASS.

Do not invent, remove, reinterpret, or compensate for structural blockers.

Decision meanings:

PASS:
- structural_pass_blockers is empty;
- every dimension is at least 6;
- evidence supports emerging and propagating attention.

HOLD:
- evidence plausibly concerns the same development and is promising,
  but support remains incomplete.

FAIL:
- evidence is irrelevant, contradictory, duplicate-only,
  unsupported, or does not materially support the claimed development.

There is NO weighted total.
Do not average dimensions.
One strong dimension cannot compensate for a weak one.

Score bands:

0-3 = unsupported
4-5 = weak or incomplete
6-7 = adequate
8-10 = strong

DIMENSION 1 - evidence_sufficiency

How much relevant downstream evidence actually supports the development?

Quantity alone is not sufficiency.

Duplicate, syndicated, and uncertain-provenance evidence must not be
treated as equivalent to additional independent confirmation.

DIMENSION 2 - independent_spread

How strongly does the packet demonstrate spread across independently
originating downstream evidence groups?

The supplied independence fields are authoritative.

Only records with:

    counts_toward_independence = true

count as established independent evidence.

Different YouTube channels, publishers, or URLs are not automatically
independent.

Uncertain, syndicated, and duplicate evidence do not count as proven
independent spread.

DIMENSION 3 - temporal_coherence

How well does reliable timing support a coherent emerging or
propagating pattern?

Use published_at only when:

    timestamp_status = reliable
    temporal_eligible = true

Multiple timestamps alone are NOT temporal propagation.

A cluster of records inside one short time window proves only
contemporaneous activity.

It does NOT, by itself, prove a change over time.

Do not describe same-window concentration as:

    a spike
    an uptick
    a surge
    growth
    acceleration
    velocity
    an increase
    rising attention

unless the packet directly contains comparative observations that
establish such a change.

This packet does not contain comparative search observations.

Do not infer comparative movement from item count.

Multiple timestamps from records that do not count toward independence
do not establish propagation across independent temporal groups.

Do not use Google observed_at as the event's start time.

Do not use Google approx_traffic as velocity, acceleration, growth,
or change over time. Google Trending RSS approx traffic is observed
magnitude, not trend slope or percent increase.

DIMENSION 4 - search_content_alignment

How well does downstream evidence match the subject, event, or
development represented by the Google wake and supplied wake context?

Google wake metadata and context refs are alignment context only.
They are not downstream evidence.

If search_wake.context_refs is empty AND the normalized query is only
the subject/entity name:

    search_content_alignment MUST NOT exceed 7.

Do not infer a more specific wake event from outside knowledge.

Do not claim that the Google wake itself identifies an injury,
incident, controversy, or other development unless supplied wake
context says so.

The downstream evidence may establish what the collected content is
about, but that does not retroactively make an entity-only Google wake
event-specific.

DIMENSION 5 - emergence_stage

How strongly does the evidence demonstrate that attention is in an
emerging AND propagating stage rather than merely being contemporaneous
or present?

A same-window cluster can support contemporaneous coverage or
contemporaneous activity.

It must not be described as a burst, wave, spike, surge, uptick,
increase, rise, growth, acceleration, momentum, or velocity unless
the packet directly contains comparative observations establishing
that change.

It cannot by itself establish propagation over time.

Established independent spread and temporal structure matter.

Do not manufacture velocity from Google's approximate traffic bucket.

For every dimension:

- cite only supplied evidence_ids;
- include only IDs materially relevant to that dimension;
- explain both strengths and limitations.

supporting_evidence_ids:

- include evidence materially supporting the overall judgment;
- do not include an ID merely because it exists.

contradictions:

- list actual tensions or contradictory evidence;
- use [] when none are established.

unknowns:

- list material unresolved facts or provenance limitations;
- do not ask for irrelevant engagement metrics merely because they
  are absent;
- engagement metrics are not required to establish emergence in this
  rubric;
- use [] only if no material unknown remains.

rationale:

- give a concise synthesis;
- distinguish contemporaneous activity from demonstrated propagation;
- do not use unsupported change-over-time language.

When the packet contains no evidence IDs, all evidence-id arrays must be empty.
""".strip()


class EvidenceAssessmentContractViolation(ValueError):
    def __init__(self, errors: tuple[str, ...]) -> None:
        self.errors = errors
        super().__init__(", ".join(errors))


def _response_schema(evidence_ids: tuple[str, ...]) -> dict[str, Any]:
    id_items: dict[str, Any] = {"type": "string"}
    if evidence_ids:
        id_items["enum"] = list(evidence_ids)

    dimension = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "score": {"type": "integer", "minimum": 0, "maximum": 10},
            "evidence_ids": {"type": "array", "items": id_items},
            "reason": {"type": "string", "minLength": 1},
        },
        "required": ["score", "evidence_ids", "reason"],
    }
    dimension_names = [
        "evidence_sufficiency",
        "independent_spread",
        "temporal_coherence",
        "search_content_alignment",
        "emergence_stage",
    ]
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "decision": {"type": "string", "enum": ["PASS", "HOLD", "FAIL"]},
            "dimensions": {
                "type": "object",
                "additionalProperties": False,
                "properties": {name: dimension for name in dimension_names},
                "required": dimension_names,
            },
            "supporting_evidence_ids": {"type": "array", "items": id_items},
            "contradictions": {"type": "array", "items": {"type": "string"}},
            "unknowns": {"type": "array", "items": {"type": "string"}},
            "rationale": {"type": "string", "minLength": 1},
        },
        "required": [
            "decision",
            "dimensions",
            "supporting_evidence_ids",
            "contradictions",
            "unknowns",
            "rationale",
        ],
    }


def _packet_payload(packet: EvidencePacket, blockers: tuple[str, ...]) -> dict[str, Any]:
    wake = packet.search_wake
    return {
        "packet_id": packet.packet_id,
        "packet_revision": packet.packet_revision,
        "lane": packet.lane.value,
        "subject": packet.subject.model_dump(mode="json"),
        "query": packet.query.model_dump(mode="json"),
        "search_wake": {
            "provider": wake.provider,
            "geo": wake.geo,
            "observed_at": wake.observed_at.isoformat(),
            "approx_traffic_raw": wake.approx_traffic_raw,
            "approx_traffic_floor": wake.approx_traffic_floor,
            "context_refs": [ref.model_dump(mode="json") for ref in wake.context_refs],
        },
        "derived_counts": packet.derived_counts.model_dump(mode="json"),
        "structural_pass_blockers": list(blockers),
        "evidence": [
            {
                "evidence_id": record.evidence_id,
                "provider": record.provider,
                "medium": record.medium,
                "source_name": record.source_name,
                "source_identity": record.source_identity,
                "title": record.title,
                "excerpt": record.excerpt,
                "published_at": record.published_at.isoformat() if record.published_at else None,
                "first_seen_at": record.first_seen_at.isoformat(),
                "timestamp_status": record.timestamp_status.value,
                "temporal_eligible": record.temporal_eligible,
                "duplicate_group_id": record.duplicate_group_id,
                "independence_group_id": record.independence_group_id,
                "independence_status": record.independence_status.value,
                "counts_toward_independence": record.counts_toward_independence,
            }
            for record in packet.evidence
        ],
    }


def judge_evidence_packet(
    *,
    packet: EvidencePacket,
    client: Any,
    model: str,
) -> EvidenceAssessment:
    blockers = structural_pass_blockers(packet)
    evidence_ids = tuple(record.evidence_id for record in packet.evidence)
    response = client.responses.create(
        model=model,
        instructions=EVIDENCE_ASSESSMENT_JUDGE_INSTRUCTIONS,
        input=json.dumps(_packet_payload(packet, blockers), ensure_ascii=False),
        store=False,
        text={
            "format": {
                "type": "json_schema",
                "name": "evidence_assessment_judgment",
                "strict": True,
                "schema": _response_schema(evidence_ids),
            }
        },
    )
    status = getattr(response, "status", None)
    if status != "completed":
        raise RuntimeError(f"{EVIDENCE_JUDGE_RESPONSE_NOT_COMPLETED}: {status}")
    output_text = getattr(response, "output_text", None)
    if not output_text:
        raise RuntimeError(EVIDENCE_JUDGE_EMPTY_OUTPUT)

    output = json.loads(output_text)
    decision = EvidenceDecision(output["decision"])
    dimensions = EvidenceDimensions.model_validate(output["dimensions"])
    assessment = EvidenceAssessment(
        assessment_version="emergence_rubric.v0.1",
        rubric_version="0.1",
        packet_id=packet.packet_id,
        packet_revision=packet.packet_revision,
        decision=decision,
        dimensions=dimensions,
        pass_blockers=() if decision == EvidenceDecision.PASS else blockers,
        supporting_evidence_ids=tuple(output["supporting_evidence_ids"]),
        contradictions=tuple(output["contradictions"]),
        unknowns=tuple(output["unknowns"]),
        rationale=output["rationale"],
        assessed_at=datetime.fromtimestamp(response.created_at, tz=timezone.utc),
        assessor_model=getattr(response, "model", None) or model,
    )
    errors = assessment_contract_errors(packet, assessment)
    if errors:
        raise EvidenceAssessmentContractViolation(errors)
    return assessment
