from __future__ import annotations

import inspect
import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from ksignal.engine.evidence import (
    CollectionRun,
    EvidenceDecision,
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
    structural_pass_blockers,
)
from ksignal.engine.evidence_assessment_judge import (
    EVIDENCE_ASSESSMENT_JUDGE_INSTRUCTIONS,
    EVIDENCE_JUDGE_EMPTY_OUTPUT,
    EVIDENCE_JUDGE_RESPONSE_NOT_COMPLETED,
    EvidenceAssessmentContractViolation,
    judge_evidence_packet,
)
from ksignal.engine.models import AccessStatus


UTC = timezone.utc
OBSERVED_AT = datetime(2026, 8, 14, 14, 0, tzinfo=UTC)
CREATED_AT = datetime(2026, 8, 14, 15, 0, tzinfo=UTC)
RESPONSE_CREATED_AT = 2_123_456_789.125


class FakeResponses:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


def model_output(
    *,
    decision="HOLD",
    ids=("news-1",),
    scores=(5, 3, 4, 7, 4),
    supporting=None,
):
    names = (
        "evidence_sufficiency",
        "independent_spread",
        "temporal_coherence",
        "search_content_alignment",
        "emergence_stage",
    )
    return {
        "decision": decision,
        "dimensions": {
            name: {
                "score": score,
                "evidence_ids": list(ids),
                "reason": f"{name} reason",
            }
            for name, score in zip(names, scores, strict=True)
        },
        "supporting_evidence_ids": list(ids if supporting is None else supporting),
        "contradictions": ["second tension", "first tension"],
        "unknowns": ["second unknown", "first unknown"],
        "rationale": "Exact model rationale — unchanged.",
    }


def fake_client(
    output,
    *,
    status="completed",
    response_model="gpt-5-mini-2025-08-07",
    created_at=RESPONSE_CREATED_AT,
    include_model=True,
):
    values = {
        "status": status,
        "output_text": None if output is None else json.dumps(output, ensure_ascii=False),
        "created_at": created_at,
    }
    if include_model:
        values["model"] = response_model
    return SimpleNamespace(responses=FakeResponses(SimpleNamespace(**values)))


def record(
    evidence_id,
    provider,
    index,
    *,
    status=IndependenceStatus.INDEPENDENT,
    counts=True,
):
    is_news = provider == "newsis"
    return EvidenceRecord(
        evidence_id=evidence_id,
        run_id=f"{provider}-run",
        provider=provider,
        medium="news" if is_news else "video",
        provider_item_id=None if is_news else f"video-{index}",
        source_name="뉴시스" if is_news else f"유튜브 채널 {index}",
        source_identity="newsis:publisher" if is_news else f"channel-{index}",
        url=f"https://must-not-be-sent.invalid/{provider}/{index}",
        title=f"임지민 관련 보도 {index}",
        excerpt=f"임지민 관련 내용 {index}",
        published_at=OBSERVED_AT,
        published_at_raw="raw",
        first_seen_at=CREATED_AT,
        timestamp_status=TimestampStatus.RELIABLE,
        temporal_eligible=True,
        duplicate_group_id=f"duplicate:{provider}:{index}",
        independence_group_id=(
            "newsis:publisher" if is_news else f"youtube:channel:{index}"
        ),
        independence_status=status,
        counts_toward_independence=counts,
    )


def packet(*, evidence=None, contexts=(), revision=3):
    if evidence is None:
        evidence = (record("news-1", "newsis", 1),)
    return EvidencePacket(
        schema_version="evidence_packet.v0.1",
        packet_id="packet-임지민-r3",
        packet_revision=revision,
        issue_id="issue-2",
        candidate_id="im-jimin",
        lane=EvidenceLane.SPORTS,
        subject=EvidenceSubject(label="임지민"),
        query=EvidenceQuery(original="임지민", normalized="임지민"),
        search_wake=SearchWake(
            provider="google_trends_rss",
            geo="KR",
            observed_at=OBSERVED_AT,
            approx_traffic_raw="1,000+",
            approx_traffic_floor=1000,
            context_refs=tuple(contexts),
        ),
        collection_runs=(
            CollectionRun(
                run_id="newsis-run",
                provider="newsis",
                operation="collect_newsis_pool",
                status=AccessStatus.CAPTURED,
                started_at=OBSERVED_AT,
                completed_at=CREATED_AT,
                raw_item_count=sum(item.provider == "newsis" for item in evidence),
                relevant_item_count=sum(item.provider == "newsis" for item in evidence),
            ),
            CollectionRun(
                run_id="youtube-run",
                provider="youtube",
                operation="collect_youtube_search",
                status=AccessStatus.CAPTURED,
                started_at=OBSERVED_AT,
                completed_at=CREATED_AT,
                raw_item_count=sum(item.provider == "youtube" for item in evidence),
                relevant_item_count=sum(item.provider == "youtube" for item in evidence),
            ),
        ),
        evidence=tuple(evidence),
        packet_created_at=CREATED_AT,
    )


def test_one_strict_call_payload_schema_and_system_owned_fields():
    context = SearchContextRef(
        title="임지민 부상 맥락", source="Google context", url="https://context.invalid/1"
    )
    item = record("news-1", "newsis", 1)
    subject_packet = packet(evidence=(item,), contexts=(context,), revision=9)
    client = fake_client(model_output())

    assessment = judge_evidence_packet(
        packet=subject_packet, client=client, model="requested-model"
    )

    assert len(client.responses.calls) == 1
    call = client.responses.calls[0]
    assert call["model"] == "requested-model" and call["store"] is False
    assert "tools" not in call
    format_ = call["text"]["format"]
    assert format_["type"] == "json_schema" and format_["strict"] is True
    schema = format_["schema"]
    assert schema["additionalProperties"] is False
    assert set(schema["properties"]) == {
        "decision", "dimensions", "supporting_evidence_ids",
        "contradictions", "unknowns", "rationale",
    }
    assert not {
        "assessment_version", "rubric_version", "packet_id", "packet_revision",
        "revision", "pass_blockers", "assessed_at", "assessor_model",
    } & set(schema["properties"])

    sent = json.loads(call["input"])
    assert set(sent) == {
        "packet_id", "packet_revision", "lane", "subject", "query", "search_wake",
        "derived_counts", "structural_pass_blockers", "evidence",
    }
    assert sent["packet_id"] == subject_packet.packet_id
    assert sent["packet_revision"] == 9 and sent["lane"] == "sports"
    assert sent["subject"]["label"] == sent["query"]["original"] == "임지민"
    assert sent["search_wake"]["context_refs"] == [context.model_dump(mode="json")]
    assert len(sent["evidence"]) == 1
    assert "url" not in sent["evidence"][0]
    assert "https://must-not-be-sent.invalid" not in call["input"]
    assert sent["structural_pass_blockers"] == list(structural_pass_blockers(subject_packet))
    assert sent["derived_counts"] == subject_packet.derived_counts.model_dump(mode="json")
    assert assessment.packet_id == subject_packet.packet_id
    assert assessment.packet_revision == 9
    assert assessment.assessment_version == "emergence_rubric.v0.1"
    assert assessment.rubric_version == "0.1"


def test_nonempty_schema_enums_exact_packet_ids_everywhere():
    evidence = (record("id-z", "newsis", 1), record("id-a", "youtube", 2))
    client = fake_client(model_output(ids=("id-z", "id-a"), supporting=("id-a", "id-z")))
    judge_evidence_packet(packet=packet(evidence=evidence), client=client, model="model")
    schema = client.responses.calls[0]["text"]["format"]["schema"]
    dimension_items = schema["properties"]["dimensions"]["properties"][
        "evidence_sufficiency"
    ]["properties"]["evidence_ids"]["items"]
    supporting_items = schema["properties"]["supporting_evidence_ids"]["items"]
    assert dimension_items["enum"] == supporting_items["enum"] == ["id-z", "id-a"]


def test_empty_packet_schema_has_valid_string_items_without_empty_enum():
    empty = packet(evidence=())
    client = fake_client(model_output(ids=(), supporting=()))
    judge_evidence_packet(packet=empty, client=client, model="model")
    schema = client.responses.calls[0]["text"]["format"]["schema"]
    items = schema["properties"]["supporting_evidence_ids"]["items"]
    assert items == {"type": "string"}
    assert "empty" in client.responses.calls[0]["instructions"].lower()


@pytest.mark.parametrize("decision", ["HOLD", "FAIL"])
def test_nonpass_preserves_exact_structural_blockers(decision):
    subject_packet = packet()
    assessment = judge_evidence_packet(
        packet=subject_packet,
        client=fake_client(model_output(decision=decision)),
        model="model",
    )
    assert assessment.decision == EvidenceDecision(decision)
    assert assessment.pass_blockers == structural_pass_blockers(subject_packet)


def test_pass_unblocked_has_no_blockers_and_preserves_all_model_order_and_metadata():
    evidence = (record("news-1", "newsis", 1), record("video-2", "youtube", 2))
    output = model_output(
        decision="PASS", ids=("video-2", "news-1"), scores=(6, 7, 8, 7, 6)
    )
    client = fake_client(output, response_model="actual-backend-model")
    assessment = judge_evidence_packet(packet=packet(evidence=evidence), client=client, model="asked")
    assert assessment.pass_blockers == ()
    assert assessment.assessed_at == datetime.fromtimestamp(RESPONSE_CREATED_AT, tz=UTC)
    assert assessment.assessor_model == "actual-backend-model"
    assert assessment.supporting_evidence_ids == ("video-2", "news-1")
    assert assessment.dimensions.evidence_sufficiency.evidence_ids == ("video-2", "news-1")
    assert assessment.contradictions == ("second tension", "first tension")
    assert assessment.unknowns == ("second unknown", "first unknown")
    assert assessment.rationale == "Exact model rationale — unchanged."


def test_assessor_model_falls_back_only_when_response_model_absent():
    assessment = judge_evidence_packet(
        packet=packet(), client=fake_client(model_output(), include_model=False), model="asked-model"
    )
    assert assessment.assessor_model == "asked-model"


def test_response_failures_are_stable_and_make_no_repair_call():
    client = fake_client(model_output(), status="in_progress")
    with pytest.raises(RuntimeError, match=EVIDENCE_JUDGE_RESPONSE_NOT_COMPLETED) as exc:
        judge_evidence_packet(packet=packet(), client=client, model="model")
    assert "in_progress" in str(exc.value) and len(client.responses.calls) == 1

    client = fake_client(None)
    with pytest.raises(RuntimeError, match=EVIDENCE_JUDGE_EMPTY_OUTPUT):
        judge_evidence_packet(packet=packet(), client=client, model="model")
    assert len(client.responses.calls) == 1


@pytest.mark.parametrize(
    ("output", "expected"),
    [
        (
            model_output(ids=("unknown-id",), supporting=()),
            "UNKNOWN_EVIDENCE_ID:evidence_sufficiency:unknown-id",
        ),
        (
            model_output(ids=(), supporting=("unknown-id",)),
            "UNKNOWN_SUPPORTING_EVIDENCE_ID:unknown-id",
        ),
    ],
)
def test_unknown_evidence_ids_fail_closed_with_exact_contract_error(output, expected):
    with pytest.raises(EvidenceAssessmentContractViolation) as exc:
        judge_evidence_packet(packet=packet(), client=fake_client(output), model="model")
    assert expected in exc.value.errors


def test_entity_only_alignment_above_seven_is_not_clamped():
    output = model_output(scores=(5, 3, 4, 8, 4))
    with pytest.raises(EvidenceAssessmentContractViolation) as exc:
        judge_evidence_packet(packet=packet(), client=fake_client(output), model="model")
    assert exc.value.errors == (
        "STRONG_SEARCH_CONTENT_ALIGNMENT_UNSUPPORTED_WITHOUT_WAKE_CONTEXT",
    )


def test_pass_against_structural_blockers_is_not_converted():
    output = model_output(decision="PASS", scores=(6, 6, 6, 7, 6))
    subject_packet = packet()
    with pytest.raises(EvidenceAssessmentContractViolation) as exc:
        judge_evidence_packet(packet=subject_packet, client=fake_client(output), model="model")
    assert exc.value.errors == tuple(
        f"PASS_STRUCTURAL_BLOCKER:{blocker}"
        for blocker in structural_pass_blockers(subject_packet)
    )


def test_pass_dimension_below_minimum_is_not_repaired():
    evidence = (record("news-1", "newsis", 1), record("video-2", "youtube", 2))
    output = model_output(decision="PASS", ids=(), scores=(6, 6, 5, 7, 6))
    with pytest.raises(EvidenceAssessmentContractViolation) as exc:
        judge_evidence_packet(packet=packet(evidence=evidence), client=fake_client(output), model="model")
    assert exc.value.errors == ("PASS_DIMENSION_BELOW_MINIMUM:temporal_coherence",)


def test_real_utf8_im_ji_min_proven_hold_wrapper_regression():
    records = [record("newsis:NISX20260814", "newsis", 0)]
    records.extend(
        record(
            f"youtube:video-{index}", "youtube", index,
            status=IndependenceStatus.UNCERTAIN, counts=False,
        )
        for index in range(4)
    )
    records.append(
        record(
            "youtube:video-4", "youtube", 4,
            status=IndependenceStatus.SYNDICATED, counts=False,
        )
    )
    subject_packet = packet(evidence=tuple(records), revision=1)
    assert subject_packet.subject.label == "임지민"
    assert subject_packet.query.original == "임지민"
    assert subject_packet.query.normalized == "임지민"
    counts = subject_packet.derived_counts
    assert (
        counts.evidence_count,
        counts.timestamped_evidence_count,
        counts.temporal_eligible_count,
        counts.independent_group_count,
        counts.provider_count,
        counts.media,
    ) == (6, 6, 6, 1, 2, ("news", "video"))
    blockers = structural_pass_blockers(subject_packet)
    assert blockers == (
        "INSUFFICIENT_INDEPENDENT_EVIDENCE",
        "INSUFFICIENT_TEMPORAL_EVIDENCE",
    )
    ids = tuple(item.evidence_id for item in records)
    assessment = judge_evidence_packet(
        packet=subject_packet,
        client=fake_client(model_output(decision="HOLD", ids=ids)),
        model="gpt-5-mini",
    )
    assert assessment.decision == EvidenceDecision.HOLD
    assert assessment.pass_blockers == blockers
    assert assessment_contract_errors(subject_packet, assessment) == ()
    assert assessment.assessor_model == "gpt-5-mini-2025-08-07"
    assert assessment.packet_id == "packet-임지민-r3"


def test_frozen_prompt_protects_proven_semantic_doctrine():
    prompt = EVIDENCE_ASSESSMENT_JUDGE_INSTRUCTIONS
    for doctrine in (
        "There is NO weighted total.",
        "counts_toward_independence = true",
        "Google approx_traffic",
        "Google observed_at",
        "contemporaneous",
        "burst",
        "spike",
        "engagement metrics are not required",
    ):
        assert doctrine in prompt
    assert "uncertain" in prompt.lower() and "syndicated" in prompt.lower()
    assert "search_content_alignment MUST NOT exceed 7" in prompt


def test_judge_source_has_no_infrastructure_environment_filesystem_or_clock_now():
    source = inspect.getsource(judge_evidence_packet)
    module_source = inspect.getsource(inspect.getmodule(judge_evidence_packet))
    assert "OpenAI(" not in module_source
    assert "OPENAI_API_KEY" not in module_source
    assert "getenv" not in module_source and "environ" not in module_source
    assert "open(" not in module_source and "Path(" not in module_source
    assert "datetime.now" not in module_source and "datetime.utcnow" not in module_source
    assert source.count("client.responses.create(") == 1
