from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ksignal.engine.evidence import (
    EvidenceAssessment,
    EvidenceDecision,
    EvidencePacket,
    EvidenceRecord,
    assessment_contract_errors,
)
from ksignal.schema import SignalCard


Category = Literal[
    "government",
    "idols",
    "sports",
    "local_phenomenon",
    "uncategorized",
]


EDITORIAL_SYNTHESIS_INSTRUCTIONS = """
You are performing editorial synthesis AFTER a separate evidence system has
already returned PASS. The assessment is a constraint, not another source of
factual observations. Every factual claim must trace to an EvidenceRecord.

You are not evaluating whether the event is emerging. You are not discovering
facts. You are not browsing. Use only the supplied EvidenceRecords and the
assessment, and return only the requested editorial fields.

Rules:
- Never add outside knowledge or turn an inference into an observed fact.
- Never use Google wake/context as reporting evidence, or a candidate absent
  from EvidencePacket.evidence.
- Never state that outlets are independent merely because they differ. Respect
  each EvidenceRecord's independence status.
- Do not claim velocity, surge, spike, momentum, acceleration, increase, rise,
  growth, or wave unless direct comparative packet evidence supports it.
- Multiple same-window timestamps alone do not prove growth. Search magnitude
  is not velocity.
- Describe comments or social reaction only when an EvidenceRecord contains it.
  Do not invent fandom reaction, public mood, or business implications.
- Keep cultural_read and business_read bounded by supplied evidence.
- If the supplied EvidenceRecords do not support a concrete
  business/market/industry implication, return business_read as an empty string.
  Never create filler merely to populate the field.
- Unknowns remain unknown. Do not silently resolve contradictions.
- raw_korean_excerpt must be copied exactly and contiguously from one supplied
  EvidenceRecord title or excerpt; never fabricate Korean source text.
- literal_translation must correspond to raw_korean_excerpt.
- Write compactly for a phone reader. Accuracy outranks cleverness.
- title_english: at most 12 words.
- cultural_read: at most 140 characters.
- raw_korean_excerpt: at most 180 characters.
- literal_translation: at most 220 characters.
- business_read: at most 280 characters.
- confidence is editorial-expression confidence: low, medium, or high.
- Evidence IDs are grounding controls; do not force them into public copy.
""".strip()


class EditorialSynthesisNotAllowed(ValueError):
    def __init__(self, code: str, details: tuple[str, ...] = ()) -> None:
        self.code = code
        self.details = details
        message = code if not details else f"{code}: {', '.join(details)}"
        super().__init__(message)


class PrimaryEvidenceNotFound(ValueError):
    def __init__(self, evidence_id: str) -> None:
        self.code = "PRIMARY_EVIDENCE_NOT_FOUND"
        self.evidence_id = evidence_id
        super().__init__(f"{self.code}: {evidence_id}")


class MalformedEditorialResponse(ValueError):
    code = "MALFORMED_MODEL_RESPONSE"

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"{self.code}: {reason}")


class UngroundedKoreanReceipt(ValueError):
    code = "UNGROUNDED_KOREAN_RECEIPT"

    def __init__(self, receipt: str) -> None:
        self.receipt = receipt
        super().__init__(self.code)


class _EditorialOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title_english: str = Field(min_length=1, max_length=100)
    raw_korean_excerpt: str = Field(min_length=1, max_length=180)
    literal_translation: str = Field(min_length=1, max_length=220)
    cultural_read: str = Field(min_length=1, max_length=140)
    business_read: str = Field(max_length=280)
    tags: list[str]
    confidence: Literal["low", "medium", "high"]


def _response_schema() -> dict[str, Any]:
    schema = _EditorialOutput.model_json_schema()
    schema["additionalProperties"] = False
    return schema


def _record_payload(record: EvidenceRecord) -> dict[str, Any]:
    return record.model_dump(mode="json")


def _assessment_payload(assessment: EvidenceAssessment) -> dict[str, Any]:
    return {
        "decision": assessment.decision.value,
        "dimensions": assessment.dimensions.model_dump(mode="json"),
        "supporting_evidence_ids": list(assessment.supporting_evidence_ids),
        "contradictions": list(assessment.contradictions),
        "unknowns": list(assessment.unknowns),
        "rationale": assessment.rationale,
    }


def _parse_output(response: Any) -> _EditorialOutput:
    if getattr(response, "status", None) != "completed":
        raise MalformedEditorialResponse(
            f"response status is {getattr(response, 'status', None)!r}"
        )
    output_text = getattr(response, "output_text", None)
    if not output_text:
        raise MalformedEditorialResponse("response has no output_text")
    try:
        return _EditorialOutput.model_validate_json(output_text)
    except (ValidationError, ValueError, TypeError) as exc:
        raise MalformedEditorialResponse("invalid structured JSON") from exc


def synthesize_pass_signal_card(
    *,
    packet: EvidencePacket,
    assessment: EvidenceAssessment,
    primary_evidence_id: str,
    category: Category,
    created_at: str,
    client: Any,
    model: str = "gpt-5-mini",
) -> SignalCard:
    errors = assessment_contract_errors(packet, assessment)
    if errors:
        raise EditorialSynthesisNotAllowed("ASSESSMENT_CONTRACT_INVALID", errors)
    if assessment.decision != EvidenceDecision.PASS:
        raise EditorialSynthesisNotAllowed(
            "ASSESSMENT_NOT_PASS", (assessment.decision.value,)
        )

    primary = next(
        (record for record in packet.evidence if record.evidence_id == primary_evidence_id),
        None,
    )
    if primary is None:
        raise PrimaryEvidenceNotFound(primary_evidence_id)
    if primary_evidence_id not in assessment.supporting_evidence_ids:
        raise EditorialSynthesisNotAllowed(
            "PRIMARY_EVIDENCE_NOT_SUPPORTING", (primary_evidence_id,)
        )

    payload = {
        "subject": packet.subject.model_dump(mode="json"),
        "query": packet.query.model_dump(mode="json"),
        "lane": packet.lane.value,
        "evidence": [_record_payload(record) for record in packet.evidence],
        "assessment": _assessment_payload(assessment),
    }
    response = client.responses.create(
        model=model,
        instructions=EDITORIAL_SYNTHESIS_INSTRUCTIONS,
        input=json.dumps(payload, ensure_ascii=False),
        store=False,
        text={
            "format": {
                "type": "json_schema",
                "name": "pass_editorial_synthesis",
                "strict": True,
                "schema": _response_schema(),
            }
        },
    )
    editorial = _parse_output(response)
    if len(editorial.title_english.split()) > 12:
        raise MalformedEditorialResponse("title_english exceeds 12 words")
    receipt = editorial.raw_korean_excerpt.strip()
    source_texts = (
        text
        for record in packet.evidence
        for text in (record.title, record.excerpt)
    )
    if not receipt or not any(receipt in text for text in source_texts):
        raise UngroundedKoreanReceipt(receipt)

    tags: list[str] = []
    for tag in editorial.tags:
        normalized = tag.strip()
        if normalized and normalized not in tags:
            tags.append(normalized)

    return SignalCard(
        source=primary.source_name,
        url=primary.url,
        category=category,
        title_original=primary.title,
        title_english=editorial.title_english,
        raw_korean_excerpt=receipt,
        literal_translation=editorial.literal_translation,
        cultural_read=editorial.cultural_read,
        business_read=editorial.business_read,
        visual_read="",
        tags=tags,
        confidence=editorial.confidence,
        translation_audit=None,
        image_paths=[],
        screenshot_paths=[],
        created_at=created_at,
    )
