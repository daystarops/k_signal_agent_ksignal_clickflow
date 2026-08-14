from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from ksignal.engine.evidence import (
    CollectionRun,
    DimensionScore,
    EvidenceAssessment,
    EvidenceDecision,
    EvidenceDimensions,
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
from ksignal.engine.models import AccessStatus


NOW = datetime(2026, 8, 13, tzinfo=timezone.utc)


def wake(raw="2000+", floor=2000, context_refs=()):
    return SearchWake(
        provider="google_trends_rss",
        geo="KR",
        observed_at=NOW,
        approx_traffic_raw=raw,
        approx_traffic_floor=floor,
        context_refs=context_refs,
    )


def run(run_id="run-youtube", provider="youtube", raw=1, relevant=1):
    return CollectionRun(
        run_id=run_id,
        provider=provider,
        operation="search",
        status=AccessStatus.CAPTURED,
        started_at=NOW,
        completed_at=NOW,
        raw_item_count=raw,
        relevant_item_count=relevant,
    )


def record(
    evidence_id="ev-1",
    run_id="run-youtube",
    provider="youtube",
    medium="video",
    group="channel-a",
    timestamp_status=TimestampStatus.RELIABLE,
    published_at=NOW,
    temporal_eligible=True,
    independence_status=IndependenceStatus.INDEPENDENT,
    counts=True,
):
    return EvidenceRecord(
        evidence_id=evidence_id,
        run_id=run_id,
        provider=provider,
        medium=medium,
        source_name=group,
        source_identity=group,
        url=f"https://example.test/{evidence_id}",
        title=evidence_id,
        excerpt="Observed evidence",
        published_at=published_at,
        first_seen_at=NOW,
        timestamp_status=timestamp_status,
        temporal_eligible=temporal_eligible,
        duplicate_group_id=evidence_id,
        independence_group_id=group,
        independence_status=independence_status,
        counts_toward_independence=counts,
    )


def packet(evidence=(), runs=None, context_refs=()):
    if runs is None:
        runs = (run(),)
    return EvidencePacket(
        schema_version="evidence_packet.v0.1",
        packet_id="packet-1",
        packet_revision=1,
        issue_id="issue-1",
        candidate_id="candidate-1",
        lane="fandom",
        subject=EvidenceSubject(label="Topic"),
        query=EvidenceQuery(original="Topic", normalized="topic"),
        search_wake=wake(context_refs=context_refs),
        collection_runs=runs,
        evidence=evidence,
        packet_created_at=NOW,
    )


def dimensions(score=6, evidence_ids=()):
    value = DimensionScore(score=score, evidence_ids=evidence_ids, reason="Supported")
    return EvidenceDimensions(
        evidence_sufficiency=value,
        independent_spread=value,
        temporal_coherence=value,
        search_content_alignment=value,
        emergence_stage=value,
    )


def assessment(target, decision=EvidenceDecision.PASS, scores=None, pass_blockers=()):
    return EvidenceAssessment(
        assessment_version="emergence_rubric.v0.1",
        rubric_version="0.1",
        packet_id=target.packet_id,
        packet_revision=target.packet_revision,
        decision=decision,
        dimensions=scores or dimensions(),
        pass_blockers=pass_blockers,
        supporting_evidence_ids=tuple(item.evidence_id for item in target.evidence),
        rationale="The evidence supports this judgment.",
        assessed_at=NOW,
        assessor_model="test-model",
    )


def valid_pass_packet():
    runs = (run(), run("run-news", "newsis"))
    evidence = (
        record(),
        record("ev-2", "run-news", "newsis", "news", "publisher-b"),
    )
    return packet(evidence, runs)


def test_google_traffic_buckets_validate_and_invalid_values_fail():
    assert wake("2000+", 2000).approx_traffic_floor == 2000
    assert wake("2,000+", 2000).approx_traffic_floor == 2000
    with pytest.raises(ValidationError):
        wake("2000+", 1000)
    with pytest.raises(ValidationError):
        wake("many+", 0)


def test_collection_run_counts():
    assert run(raw=0, relevant=0).status == AccessStatus.CAPTURED
    with pytest.raises(ValidationError):
        run(raw=1, relevant=2)


@pytest.mark.parametrize(
    ("timestamp_status", "published_at", "temporal_eligible"),
    [
        (TimestampStatus.RELIABLE, None, True),
        (TimestampStatus.RELIABLE, NOW, False),
        (TimestampStatus.AMBIGUOUS, NOW, True),
        (TimestampStatus.MISSING, None, True),
    ],
)
def test_timestamp_rules(timestamp_status, published_at, temporal_eligible):
    with pytest.raises(ValidationError):
        record(
            timestamp_status=timestamp_status,
            published_at=published_at,
            temporal_eligible=temporal_eligible,
        )


@pytest.mark.parametrize(
    "status",
    [
        IndependenceStatus.DUPLICATE,
        IndependenceStatus.SYNDICATED,
        IndependenceStatus.UNCERTAIN,
    ],
)
def test_only_independent_evidence_can_count(status):
    with pytest.raises(ValidationError):
        record(independence_status=status, counts=True)


def test_packet_rejects_duplicate_run_ids():
    with pytest.raises(ValidationError):
        packet(runs=(run(), run()))


def test_packet_rejects_duplicate_evidence_ids():
    with pytest.raises(ValidationError):
        packet((record(), record()))


def test_packet_rejects_unknown_run():
    with pytest.raises(ValidationError):
        packet((record(run_id="unknown"),))


def test_packet_rejects_provider_mismatch():
    with pytest.raises(ValidationError):
        packet((record(provider="newsis"),))


def test_derived_counts_deduplicate_groups_and_sort_media():
    runs = (run(raw=2, relevant=2), run("run-news", "newsis"))
    evidence = (
        record(),
        record("ev-2", group="channel-a"),
        record("ev-3", "run-news", "newsis", "news", "publisher-b"),
    )
    counts = packet(evidence, runs).derived_counts
    assert counts.evidence_count == 3
    assert counts.timestamped_evidence_count == 3
    assert counts.temporal_eligible_count == 3
    assert counts.independent_group_count == 2
    assert counts.provider_count == 2
    assert counts.media == ("news", "video")


def test_derived_counts_serialization_round_trips_and_recomputes():
    target = valid_pass_packet()
    dumped = target.model_dump(mode="json")

    assert "derived_counts" in dumped
    assert EvidencePacket.model_validate(dumped) == target
    assert EvidencePacket.model_validate_json(target.model_dump_json()) == target

    dumped["derived_counts"]["independent_group_count"] = 999
    loaded = EvidencePacket.model_validate(dumped)
    assert loaded.derived_counts.independent_group_count == 2


def test_packet_still_rejects_unknown_extra_fields():
    dumped = valid_pass_packet().model_dump(mode="json")
    dumped["unknown_field"] = "forbidden"

    with pytest.raises(ValidationError):
        EvidencePacket.model_validate(dumped)


def test_context_refs_do_not_affect_counts_and_empty_evidence_is_zeroed():
    ref = SearchContextRef(title="Context", source="Google", url="https://example.test")
    counts = packet(context_refs=(ref,)).derived_counts
    assert counts.evidence_count == 0
    assert counts.timestamped_evidence_count == 0
    assert counts.temporal_eligible_count == 0
    assert counts.independent_group_count == 0
    assert counts.provider_count == 0
    assert counts.media == ()


def test_structural_blockers_require_independent_temporal_groups():
    one_group = packet((record(), record("ev-2")), (run(raw=2, relevant=2),))
    blockers = structural_pass_blockers(one_group)
    assert "INSUFFICIENT_INDEPENDENT_EVIDENCE" in blockers
    assert "INSUFFICIENT_TEMPORAL_EVIDENCE" in blockers

    runs = (run(), run("run-news", "newsis"))
    second_not_temporal = record(
        "ev-2",
        "run-news",
        "newsis",
        "news",
        "publisher-b",
        TimestampStatus.MISSING,
        None,
        False,
    )
    blockers = structural_pass_blockers(packet((record(), second_not_temporal), runs))
    assert "INSUFFICIENT_INDEPENDENT_EVIDENCE" not in blockers
    assert "INSUFFICIENT_TEMPORAL_EVIDENCE" in blockers
    assert structural_pass_blockers(valid_pass_packet()) == ()


def test_empty_packet_structural_blocker_order():
    assert structural_pass_blockers(packet(())) == (
        "NO_RELEVANT_DOWNSTREAM_EVIDENCE",
        "INSUFFICIENT_INDEPENDENT_EVIDENCE",
        "INSUFFICIENT_TEMPORAL_EVIDENCE",
    )


def test_dimension_score_range_and_unique_references():
    for invalid in (-1, 11):
        with pytest.raises(ValidationError):
            DimensionScore(score=invalid, reason="Invalid")
    with pytest.raises(ValidationError):
        DimensionScore(score=6, evidence_ids=("ev-1", "ev-1"), reason="Duplicate")


def test_valid_pass_has_no_contract_errors():
    target = valid_pass_packet()
    assessed = assessment(target, scores=dimensions(6, ("ev-1",)))
    assert assessment_contract_errors(target, assessed) == ()


def test_pass_dimension_below_six_is_an_error():
    target = valid_pass_packet()
    errors = assessment_contract_errors(target, assessment(target, scores=dimensions(5)))
    assert any(error.startswith("PASS_DIMENSION_BELOW_MINIMUM:") for error in errors)


def test_pass_with_one_group_or_declared_blocker_is_an_error():
    incomplete = packet((record(),))
    errors = assessment_contract_errors(incomplete, assessment(incomplete))
    assert any(error.startswith("PASS_STRUCTURAL_BLOCKER:") for error in errors)

    target = valid_pass_packet()
    errors = assessment_contract_errors(
        target, assessment(target, pass_blockers=("MANUAL_BLOCKER",))
    )
    assert "PASS_BLOCKERS_MUST_BE_EMPTY" in errors


def test_wrong_revision_and_unknown_evidence_references_are_errors():
    target = valid_pass_packet()
    wrong_revision = assessment(target).model_copy(update={"packet_revision": 2})
    assert "PACKET_REVISION_MISMATCH" in assessment_contract_errors(target, wrong_revision)

    bad_dimensions = dimensions(6, ("absent",))
    bad_reference = assessment(target, scores=bad_dimensions)
    assert any("absent" in error for error in assessment_contract_errors(target, bad_reference))


def test_packet_id_mismatch_is_an_error():
    target = valid_pass_packet()
    wrong_packet = assessment(target).model_copy(update={"packet_id": "packet-2"})
    assert assessment_contract_errors(target, wrong_packet) == ("PACKET_ID_MISMATCH",)


def test_unknown_supporting_evidence_id_is_an_error():
    target = valid_pass_packet()
    bad_reference = assessment(target).model_copy(
        update={"supporting_evidence_ids": ("absent",)}
    )
    assert assessment_contract_errors(target, bad_reference) == (
        "UNKNOWN_SUPPORTING_EVIDENCE_ID:absent",
    )


def test_hold_is_allowed_on_structurally_incomplete_packet():
    target = packet(())
    held = assessment(target, decision=EvidenceDecision.HOLD, scores=dimensions(2))
    assert assessment_contract_errors(target, held) == ()


def test_contract_objects_are_frozen():
    target = valid_pass_packet()
    with pytest.raises(ValidationError):
        target.packet_revision = 2
    with pytest.raises(ValidationError):
        target.evidence[0].title = "Changed"
