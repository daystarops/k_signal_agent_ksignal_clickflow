from __future__ import annotations

import inspect
import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from ksignal.engine.evidence import (
    CollectionRun,
    DimensionScore,
    EvidenceAssessment,
    EvidenceDecision,
    EvidenceDimensions,
    EvidenceLane,
    EvidencePacket,
    EvidenceQuery,
    EvidenceRecord,
    EvidenceSubject,
    IndependenceStatus,
    SearchContextRef,
    SearchWake,
    TimestampStatus,
    assessment_contract_errors,
)
from ksignal.engine.models import AccessStatus
from ksignal.engine.pass_editorial_synthesis import (
    EDITORIAL_SYNTHESIS_INSTRUCTIONS,
    EditorialSynthesisNotAllowed,
    MalformedEditorialResponse,
    PrimaryEvidenceNotFound,
    UngroundedKoreanReceipt,
    synthesize_pass_signal_card,
)


NOW = datetime(2026, 8, 15, 12, 0, tzinfo=timezone.utc)
CREATED_AT = "2026-08-15T12:30:00+00:00"


class FakeResponses:
    def __init__(self, output):
        self.calls = []
        self.output = output

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            status="completed",
            output_text=json.dumps(self.output, ensure_ascii=False),
        )


def editorial_output(**updates):
    value = {
        "title_english": "Two outlets document the approved development",
        "raw_korean_excerpt": "송가인 새 무대 공개",
        "literal_translation": "Song Ga-in reveals a new stage.",
        "cultural_read": "Two reports document the same bounded development.",
        "business_read": "The supplied reports support attention to the new stage, no more.",
        "tags": [" 트로트 ", "무대", "트로트"],
        "confidence": "high",
    }
    value.update(updates)
    return value


def record(evidence_id, provider, source, title, excerpt, hour):
    return EvidenceRecord(
        evidence_id=evidence_id,
        run_id=f"run-{provider}",
        provider=provider,
        medium="news" if provider == "news" else "video",
        provider_item_id=f"item-{evidence_id}",
        source_name=source,
        source_identity=f"identity-{provider}",
        url=f"https://evidence.example/{evidence_id}",
        title=title,
        excerpt=excerpt,
        published_at=NOW.replace(hour=hour),
        published_at_raw=f"2026-08-15 {hour}:00",
        first_seen_at=NOW,
        timestamp_status=TimestampStatus.RELIABLE,
        temporal_eligible=True,
        duplicate_group_id=f"duplicate-{evidence_id}",
        independence_group_id=f"independent-{provider}",
        independence_status=IndependenceStatus.INDEPENDENT,
        counts_toward_independence=True,
    )


def pass_packet():
    evidence = (
        record(
            "news-송가인",
            "news",
            "한국일보",
            "송가인 새 무대 공개",
            "가수 송가인이 새로운 무대를 공개했다.",
            9,
        ),
        record(
            "video-송가인",
            "youtube",
            "공식 채널",
            "송가인 무대 영상",
            "송가인 공연 영상이 공개됐다.",
            11,
        ),
    )
    runs = tuple(
        CollectionRun(
            run_id=f"run-{provider}",
            provider=provider,
            operation="collect",
            status=AccessStatus.CAPTURED,
            started_at=NOW,
            completed_at=NOW,
            raw_item_count=1,
            relevant_item_count=1,
        )
        for provider in ("news", "youtube")
    )
    return EvidencePacket(
        schema_version="evidence_packet.v0.1",
        packet_id="pass-packet-송가인",
        packet_revision=1,
        issue_id="issue-pass",
        candidate_id="separate-hypothetical-pass",
        lane=EvidenceLane.FANDOM,
        subject=EvidenceSubject(label="송가인"),
        query=EvidenceQuery(original="송가인 새 무대", normalized="송가인 새 무대"),
        search_wake=SearchWake(
            provider="google_trends_rss",
            geo="KR",
            observed_at=NOW,
            approx_traffic_raw="2,000+",
            approx_traffic_floor=2000,
            context_refs=(
                SearchContextRef(
                    title="GOOGLE CONTEXT MUST NOT LEAK",
                    source="Google",
                    url="https://google-context.invalid/secret",
                ),
            ),
        ),
        collection_runs=runs,
        evidence=evidence,
        packet_created_at=NOW,
    )


def dimensions(ids):
    score = DimensionScore(score=7, evidence_ids=ids, reason="Packet evidence supports it.")
    return EvidenceDimensions(
        evidence_sufficiency=score,
        independent_spread=score,
        temporal_coherence=score,
        search_content_alignment=score,
        emergence_stage=score,
    )


def assessment(packet, decision=EvidenceDecision.PASS, supporting=None):
    ids = tuple(item.evidence_id for item in packet.evidence)
    return EvidenceAssessment(
        assessment_version="emergence_rubric.v0.1",
        rubric_version="0.1",
        packet_id=packet.packet_id,
        packet_revision=packet.packet_revision,
        decision=decision,
        dimensions=dimensions(ids),
        pass_blockers=(),
        supporting_evidence_ids=ids if supporting is None else supporting,
        contradictions=("The sources differ on framing.",),
        unknowns=("Audience reaction is unknown.",),
        rationale="The separate evidence judgment passed this packet.",
        assessed_at=NOW,
        assessor_model="judge-model",
    )


def client(output=None):
    return SimpleNamespace(responses=FakeResponses(output or editorial_output()))


def synthesize(packet=None, assessed=None, fake=None, primary_id="news-송가인", **kwargs):
    packet = packet or pass_packet()
    assessed = assessed or assessment(packet)
    fake = fake or client()
    card = synthesize_pass_signal_card(
        packet=packet,
        assessment=assessed,
        primary_evidence_id=primary_id,
        category=kwargs.get("category", "local_phenomenon"),
        created_at=CREATED_AT,
        client=fake,
        model=kwargs.get("model", "caller-model-exact"),
    )
    return card, fake


def test_valid_pass_makes_one_strict_caller_owned_call_and_returns_card():
    packet = pass_packet()
    assert assessment_contract_errors(packet, assessment(packet)) == ()
    card, fake = synthesize(packet=packet)

    assert len(fake.responses.calls) == 1
    call = fake.responses.calls[0]
    assert call["model"] == "caller-model-exact"
    assert call["store"] is False
    assert "tools" not in call
    format_ = call["text"]["format"]
    assert format_["type"] == "json_schema" and format_["strict"] is True
    assert format_["schema"]["additionalProperties"] is False
    assert set(format_["schema"]["properties"]) == {
        "title_english", "raw_korean_excerpt", "literal_translation",
        "cultural_read", "business_read", "tags", "confidence",
    }
    assert card.source == "한국일보"
    assert card.url == "https://evidence.example/news-송가인"
    assert card.category == "local_phenomenon"
    assert card.title_original == "송가인 새 무대 공개"
    assert card.created_at == CREATED_AT
    assert card.image_paths == [] and card.screenshot_paths == []
    assert card.translation_audit is None and card.visual_read == ""
    assert card.literal_translation == "Song Ga-in reveals a new stage."
    assert card.tags == ["트로트", "무대"]


@pytest.mark.parametrize("decision", [EvidenceDecision.HOLD, EvidenceDecision.FAIL])
def test_non_pass_refuses_before_model_call(decision):
    packet = pass_packet()
    fake = client()
    with pytest.raises(EditorialSynthesisNotAllowed) as exc:
        synthesize(packet=packet, assessed=assessment(packet, decision), fake=fake)
    assert exc.value.code == "ASSESSMENT_NOT_PASS"
    assert fake.responses.calls == []


def test_contract_invalid_refuses_before_model_call():
    packet = pass_packet()
    invalid = assessment(packet).model_copy(update={"packet_revision": 2})
    fake = client()
    with pytest.raises(EditorialSynthesisNotAllowed) as exc:
        synthesize(packet=packet, assessed=invalid, fake=fake)
    assert exc.value.code == "ASSESSMENT_CONTRACT_INVALID"
    assert "PACKET_REVISION_MISMATCH" in exc.value.details
    assert fake.responses.calls == []


def test_primary_lookup_is_exact_and_missing_has_explicit_error():
    packet = pass_packet()
    for value in ("NEWS-송가인", "news-송가인 ", "news-"):
        fake = client()
        with pytest.raises(PrimaryEvidenceNotFound) as exc:
            synthesize(packet=packet, fake=fake, primary_id=value)
        assert exc.value.code == "PRIMARY_EVIDENCE_NOT_FOUND"
        assert fake.responses.calls == []


def test_primary_must_be_cited_by_pass_assessment():
    packet = pass_packet()
    assessed = assessment(packet, supporting=("video-송가인",))
    fake = client()
    with pytest.raises(EditorialSynthesisNotAllowed) as exc:
        synthesize(packet=packet, assessed=assessed, fake=fake)
    assert exc.value.code == "PRIMARY_EVIDENCE_NOT_SUPPORTING"
    assert fake.responses.calls == []


def test_payload_contains_only_packet_evidence_and_no_google_context():
    packet = pass_packet()
    _, fake = synthesize(packet=packet)
    call = fake.responses.calls[0]
    sent = json.loads(call["input"])
    assert set(sent) == {"subject", "query", "lane", "evidence", "assessment"}
    assert [item["evidence_id"] for item in sent["evidence"]] == [
        "news-송가인", "video-송가인"
    ]
    serialized = call["input"]
    assert "GOOGLE CONTEXT MUST NOT LEAK" not in serialized
    assert "google-context.invalid" not in serialized
    assert "search_wake" not in serialized
    assert "candidate" not in serialized


def test_model_cannot_override_wrapper_owned_fields():
    output = editorial_output(
        source="attacker", url="https://attacker.invalid", category="idols",
        title_original="invented", created_at="tomorrow",
    )
    with pytest.raises(MalformedEditorialResponse):
        synthesize(fake=client(output))


def test_exact_korean_receipt_and_outer_whitespace_succeed():
    card, _ = synthesize(fake=client(editorial_output(raw_korean_excerpt="  송가인 새 무대 공개\n")))
    assert card.raw_korean_excerpt == "송가인 새 무대 공개"


def test_empty_business_read_succeeds_without_wrapper_filler():
    card, _ = synthesize(fake=client(editorial_output(business_read="")))
    assert card.business_read == ""


def test_exactly_twelve_word_title_succeeds():
    title = "One two three four five six seven eight nine ten eleven twelve"
    card, _ = synthesize(fake=client(editorial_output(title_english=title)))
    assert card.title_english == title


def test_thirteen_word_title_fails_closed_without_retry():
    title = "One two three four five six seven eight nine ten eleven twelve thirteen"
    fake = client(editorial_output(title_english=title))
    with pytest.raises(
        MalformedEditorialResponse,
        match="title_english exceeds 12 words",
    ):
        synthesize(fake=fake)
    assert len(fake.responses.calls) == 1


@pytest.mark.parametrize("receipt", ["송가인 인기가 폭발했다", "송가인  새 무대 공개"])
def test_fabricated_or_fuzzy_korean_receipt_fails_closed(receipt):
    with pytest.raises(UngroundedKoreanReceipt):
        synthesize(fake=client(editorial_output(raw_korean_excerpt=receipt)))


@pytest.mark.parametrize(
    "updates",
    [
        {"confidence": "certain"},
        {"raw_korean_excerpt": "송" * 181},
        {"literal_translation": "x" * 221},
        {"cultural_read": "x" * 141},
        {"business_read": "x" * 281},
    ],
)
def test_malformed_structured_output_fails_closed(updates):
    with pytest.raises(MalformedEditorialResponse):
        synthesize(fake=client(editorial_output(**updates)))


def test_schema_and_prompt_freeze_editorial_constraints():
    _, fake = synthesize()
    schema = fake.responses.calls[0]["text"]["format"]["schema"]
    properties = schema["properties"]
    assert properties["raw_korean_excerpt"]["maxLength"] == 180
    assert properties["literal_translation"]["maxLength"] == 220
    assert properties["cultural_read"]["maxLength"] == 140
    assert properties["business_read"]["maxLength"] == 280
    assert properties["confidence"]["enum"] == ["low", "medium", "high"]
    for phrase in (
        "title_english: at most 12 words",
        "assessment is a constraint",
        "Multiple same-window timestamps alone do not prove growth",
        "raw_korean_excerpt must be copied exactly",
    ):
        assert phrase in EDITORIAL_SYNTHESIS_INSTRUCTIONS


def test_production_module_has_no_forbidden_infrastructure_or_legacy_path():
    module = inspect.getmodule(synthesize_pass_signal_card)
    source = inspect.getsource(module)
    function_source = inspect.getsource(synthesize_pass_signal_card)
    for forbidden in (
        "OpenAI(", "OPENAI_API_KEY", "OPENAI_TEXT_MODEL", "getenv", "environ",
        "datetime.now", "datetime.utcnow", "create_signal_card", "audit_translation",
        "open(", "write_text", "write_bytes", "render_issue", "rebuild_issue",
        "publisher",
    ):
        assert forbidden not in source
    assert function_source.count("client.responses.create(") == 1
