from __future__ import annotations

import inspect
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

import ksignal.engine.sunday_run as sunday
from ksignal.engine.evidence import EvidenceDecision, EvidenceQuery, EvidenceSubject
from ksignal.engine.newsis_candidate_narrowing import (
    NewsisCandidateSelection,
    NewsisNarrowedCandidate,
)
from ksignal.engine.relevance_classifier import RelevanceProvider
from ksignal.engine.source_collectors import GoogleContextRef, GoogleWakeCandidate
from ksignal.engine.wake_classifier import LaneConfidence, WakeLane, WakeLaneClassification


UTC = timezone.utc
OBSERVED = datetime(2026, 8, 14, 14, 7, tzinfo=UTC)
PUBLISHED_AFTER = datetime(2021, 2, 3, 4, 5, 6, tzinfo=UTC)
CREATED = datetime(2026, 8, 15, 9, 10, tzinfo=UTC)
NEWSIS_COMPLETED = datetime(2026, 8, 15, 9, 1, tzinfo=UTC)
YOUTUBE_COMPLETED = datetime(2026, 8, 15, 9, 2, tzinfo=UTC)


def wake() -> GoogleWakeCandidate:
    return GoogleWakeCandidate(
        query="송가인",
        observed_at=OBSERVED,
        approx_traffic_raw="2,000+",
        approx_traffic_floor=2000,
        context_refs=tuple(
            GoogleContextRef(title=f"송가인 맥락 {index}", source="source", url=f"https://context/{index}")
            for index in range(3)
        ),
    )


def classification(lane: WakeLane = WakeLane.BEAUTY) -> WakeLaneClassification:
    return WakeLaneClassification(
        query="송가인", lane=lane, confidence=LaneConfidence.HIGH, reason="fixture"
    )


def narrowed(index: int) -> NewsisNarrowedCandidate:
    return NewsisNarrowedCandidate(
        url=f"https://newsis.example/article/{index}?ar_id=NISX-unrelated-{index}",
        feeds=("entertain",),
        title=f"Newsis {index}",
        description=f"description {index}",
        published_at_raw="Fri, 14 Aug 2026 10:00:00 +0900",
        literal_match=False,
        semantic_score=0.5,
        selected_by=NewsisCandidateSelection.SEMANTIC,
    )


def result_args(subject=None, query=None):
    selected = wake()
    return {
        "wake": selected,
        "subject": subject or EvidenceSubject(label="송가인"),
        "query": query or EvidenceQuery(original="송가인", normalized="송가인"),
        "youtube_published_after": PUBLISHED_AFTER,
        "newsis_candidate_ids_by_url": {},
        "issue_id": "issue-caller",
        "candidate_id": "candidate-caller",
        "packet_id": "packet-caller",
        "packet_revision": 17,
        "packet_created_at": CREATED,
        "newsis_run_id": "newsis-run-caller",
        "youtube_run_id": "youtube-run-caller",
        "openai_client": object(),
        "youtube_api_key": "youtube-key-caller",
        "http_client": object(),
        "lane_model": "lane-caller",
        "narrowing_model": "narrow-caller",
        "relevance_model": "relevance-caller",
        "independence_model": "independence-caller",
        "assessment_model": "assessment-caller",
    }


def test_lane_call_requires_one_exact_matching_classification_and_forwards_model(monkeypatch):
    args = result_args()
    calls = []

    def fake_lane(wakes, client, model):
        calls.append((wakes, client, model))
        return SimpleNamespace(classifications=(classification(WakeLane.OUT_OF_SCOPE),))

    monkeypatch.setattr(sunday, "classify_wake_lanes", fake_lane)
    sunday.run_selected_wake(**args)
    assert calls == [((args["wake"],), args["openai_client"], "lane-caller")]

    monkeypatch.setattr(sunday, "classify_wake_lanes", lambda *a, **k: SimpleNamespace(classifications=()))
    with pytest.raises(ValueError, match="exactly one"):
        sunday.run_selected_wake(**args)
    mismatch = classification(WakeLane.OUT_OF_SCOPE).model_copy(update={"query": " 송가인 "})
    monkeypatch.setattr(
        sunday,
        "classify_wake_lanes",
        lambda *a, **k: SimpleNamespace(classifications=(mismatch,)),
    )
    with pytest.raises(ValueError, match="match selected wake exactly"):
        sunday.run_selected_wake(**args)


def test_out_of_scope_is_exact_normal_terminal_result_with_zero_downstream_calls(monkeypatch):
    selected = classification(WakeLane.OUT_OF_SCOPE)
    monkeypatch.setattr(
        sunday,
        "classify_wake_lanes",
        lambda *a, **k: SimpleNamespace(classifications=(selected,)),
    )

    def forbidden(*args, **kwargs):
        raise AssertionError("downstream component called")

    for name in (
        "collect_newsis_pool",
        "collect_youtube_search",
        "narrow_newsis_candidates",
        "prepare_newsis_candidates",
        "prepare_youtube_candidates",
        "classify_candidate_relevance",
        "classify_candidate_independence",
        "build_evidence_records",
        "assemble_evidence_packet",
        "judge_evidence_packet",
    ):
        monkeypatch.setattr(sunday, name, forbidden)
    result = sunday.run_selected_wake(**result_args())
    assert isinstance(result, sunday.SundayOutOfScopeResult)
    assert result.lane_classification is selected
    assert result.status == "out_of_scope"


def install_pipeline(monkeypatch, *, newsis_count=2, youtube_count=2, relevant_ids=None):
    selected = classification()
    narrowed_items = tuple(narrowed(index) for index in range(newsis_count))
    newsis_collection = SimpleNamespace(items=("raw-newsis",), completed_at=NEWSIS_COMPLETED)
    youtube_collection = SimpleNamespace(items=("raw-youtube",), completed_at=YOUTUBE_COMPLETED)
    calls = {}

    monkeypatch.setattr(
        sunday,
        "classify_wake_lanes",
        lambda wakes, client, model: SimpleNamespace(classifications=(selected,)),
    )

    def collect_newsis_pool(*, client):
        calls.setdefault("newsis_collect", []).append(client)
        return newsis_collection

    def collect_youtube_search(query, published_after, api_key, *, client):
        calls.setdefault("youtube_collect", []).append((query, published_after, api_key, client))
        return youtube_collection

    def narrow_newsis_candidates(*, wakes, items, client, model):
        calls["narrow"] = (wakes, items, client, model)
        return SimpleNamespace(results=(SimpleNamespace(query="송가인", candidates=narrowed_items),))

    def prepare_newsis_candidates(*, bindings, collection):
        calls["newsis_prepare"] = (bindings, collection)
        return tuple(
            SimpleNamespace(
                source=SimpleNamespace(
                    candidate=SimpleNamespace(candidate_id=binding.candidate_id, provider=RelevanceProvider.NEWSIS)
                ),
                independence_candidate=SimpleNamespace(
                    candidate_id=binding.candidate_id, provider=RelevanceProvider.NEWSIS
                ),
            )
            for binding in bindings
        )

    def prepare_youtube_candidates(*, collection):
        calls["youtube_prepare"] = collection
        return tuple(
            SimpleNamespace(
                source=SimpleNamespace(
                    candidate=SimpleNamespace(candidate_id=f"youtube:{index}", provider=RelevanceProvider.YOUTUBE)
                ),
                independence_candidate=SimpleNamespace(
                    candidate_id=f"youtube:{index}", provider=RelevanceProvider.YOUTUBE
                ),
            )
            for index in range(youtube_count)
        )

    def classify_candidate_relevance(selected_wake, candidates, client, model):
        calls["relevance"] = (selected_wake, candidates, client, model)
        ids = relevant_ids if relevant_ids is not None else {candidates[0].candidate_id}
        return SimpleNamespace(
            results=tuple(
                SimpleNamespace(candidate_id=item.candidate_id, relevant=item.candidate_id in ids)
                for item in candidates
            )
        )

    def classify_candidate_independence(*, candidates, client, model):
        calls["independence"] = (candidates, client, model)
        return SimpleNamespace(
            results=tuple(SimpleNamespace(candidate_id=item.candidate_id) for item in candidates)
        )

    evidence = (SimpleNamespace(evidence_id="explicit-id-alpha"),)

    def build_evidence_records(**kwargs):
        calls["bridge"] = kwargs
        return evidence if kwargs["independence_assignments"] else ()

    packet = SimpleNamespace(
        derived_counts=SimpleNamespace(
            evidence_count=1,
            timestamped_evidence_count=1,
            temporal_eligible_count=1,
            independent_group_count=1,
            provider_count=1,
            media=("news",),
        )
    )

    def assemble_evidence_packet(**kwargs):
        calls["assemble"] = kwargs
        return packet

    assessment = SimpleNamespace(
        decision=EvidenceDecision.HOLD,
        pass_blockers=(
            "INSUFFICIENT_INDEPENDENT_EVIDENCE",
            "INSUFFICIENT_TEMPORAL_EVIDENCE",
        ),
        contract_errors=(),
    )

    def judge_evidence_packet(**kwargs):
        calls["judge"] = kwargs
        return assessment

    for name, fake in (
        ("collect_newsis_pool", collect_newsis_pool),
        ("collect_youtube_search", collect_youtube_search),
        ("narrow_newsis_candidates", narrow_newsis_candidates),
        ("prepare_newsis_candidates", prepare_newsis_candidates),
        ("prepare_youtube_candidates", prepare_youtube_candidates),
        ("classify_candidate_relevance", classify_candidate_relevance),
        ("classify_candidate_independence", classify_candidate_independence),
        ("build_evidence_records", build_evidence_records),
        ("assemble_evidence_packet", assemble_evidence_packet),
        ("judge_evidence_packet", judge_evidence_packet),
    ):
        monkeypatch.setattr(sunday, name, fake)
    return calls, narrowed_items, newsis_collection, youtube_collection, packet, assessment, selected


def test_in_scope_composes_exact_calls_order_bindings_contexts_and_outputs(monkeypatch):
    calls, narrowed_items, newsis_collection, youtube_collection, packet, assessment, selected = install_pipeline(monkeypatch)
    args = result_args()
    args["newsis_candidate_ids_by_url"] = {
        narrowed_items[0].url: "explicit-id-alpha",
        narrowed_items[1].url: "totally-unrelated-beta",
        "https://stale.example/": "ignored-extra",
    }
    result = sunday.run_selected_wake(**args)

    assert calls["newsis_collect"] == [args["http_client"]]
    assert calls["youtube_collect"] == [
        ("송가인", PUBLISHED_AFTER, "youtube-key-caller", args["http_client"])
    ]
    assert calls["narrow"] == (
        (args["wake"],), newsis_collection.items, args["openai_client"], "narrow-caller"
    )
    bindings, bound_collection = calls["newsis_prepare"]
    assert bound_collection is newsis_collection
    assert tuple(binding.narrowed for binding in bindings) == narrowed_items
    assert tuple(binding.candidate_id for binding in bindings) == (
        "explicit-id-alpha", "totally-unrelated-beta"
    )
    assert calls["youtube_prepare"] is youtube_collection

    relevance_wake, relevance_candidates, relevance_client, relevance_model = calls["relevance"]
    assert relevance_wake is args["wake"] and relevance_client is args["openai_client"]
    assert relevance_model == "relevance-caller"
    assert tuple(item.candidate_id for item in relevance_candidates) == (
        "explicit-id-alpha", "totally-unrelated-beta", "youtube:0", "youtube:1"
    )
    independence_candidates, independence_client, independence_model = calls["independence"]
    assert tuple(item.candidate_id for item in independence_candidates) == ("explicit-id-alpha",)
    assert independence_client is args["openai_client"] and independence_model == "independence-caller"

    bridge = calls["bridge"]
    assert tuple(source.candidate.candidate_id for source in bridge["sources"]) == tuple(
        item.candidate_id for item in relevance_candidates
    )
    assert len(bridge["relevance_results"]) == 4
    assert tuple(item.candidate_id for item in bridge["independence_assignments"]) == ("explicit-id-alpha",)
    contexts = bridge["collection_contexts"]
    assert [(item.provider, item.run_id, item.completed_at) for item in contexts] == [
        (RelevanceProvider.NEWSIS, "newsis-run-caller", NEWSIS_COMPLETED),
        (RelevanceProvider.YOUTUBE, "youtube-run-caller", YOUTUBE_COMPLETED),
    ]

    assembled = calls["assemble"]
    for key in (
        "packet_id", "packet_revision", "issue_id", "candidate_id", "packet_created_at",
        "newsis_run_id", "youtube_run_id",
    ):
        assert assembled[key] == args[key]
    assert assembled["subject"] is args["subject"]
    assert assembled["query"] is args["query"]
    assert assembled["wake"] is args["wake"] and assembled["lane_classification"] is selected
    assert assembled["newsis_collection"] is newsis_collection
    assert assembled["youtube_collection"] is youtube_collection
    assert calls["judge"] == {
        "packet": packet, "client": args["openai_client"], "model": "assessment-caller"
    }
    assert isinstance(result, sunday.SundayAssessedResult)
    assert result.packet is packet and result.assessment is assessment
    assert set(result.__dataclass_fields__) == {"lane_classification", "packet", "assessment", "status"}


def test_missing_ids_preserve_narrowing_order_and_stop_before_preparation(monkeypatch):
    calls, narrowed_items, *_ = install_pipeline(monkeypatch, newsis_count=3)
    args = result_args()
    args["newsis_candidate_ids_by_url"] = {narrowed_items[1].url: "present"}

    def forbidden(*args, **kwargs):
        raise AssertionError("preparation or later call")

    for name in (
        "prepare_newsis_candidates", "prepare_youtube_candidates",
        "classify_candidate_relevance", "classify_candidate_independence",
        "build_evidence_records", "assemble_evidence_packet", "judge_evidence_packet",
    ):
        monkeypatch.setattr(sunday, name, forbidden)
    with pytest.raises(sunday.MissingNewsisCandidateIds) as exc:
        sunday.run_selected_wake(**args)
    assert exc.value.urls == (narrowed_items[0].url, narrowed_items[2].url)
    assert len(calls["newsis_collect"]) == len(calls["youtube_collect"]) == 1


def test_zero_relevant_uses_empty_independence_and_continues(monkeypatch):
    calls, narrowed_items, *rest = install_pipeline(monkeypatch, relevant_ids=set())
    args = result_args()
    args["newsis_candidate_ids_by_url"] = {item.url: f"id-{index}" for index, item in enumerate(narrowed_items)}
    result = sunday.run_selected_wake(**args)
    assert calls["independence"][0] == ()
    assert calls["bridge"]["independence_assignments"] == ()
    assert calls["assemble"]["evidence"] == ()
    assert isinstance(result, sunday.SundayAssessedResult)


def test_song_ga_in_proven_composition_shape_regression(monkeypatch):
    relevant = {"news-explicit-opaque"}
    calls, narrowed_items, _, _, packet, assessment, _ = install_pipeline(
        monkeypatch, newsis_count=4, youtube_count=5, relevant_ids=relevant
    )
    args = result_args()
    ids = ("news-explicit-opaque", "blue", "candidate-without-nisx", "fourth")
    args["newsis_candidate_ids_by_url"] = dict(zip((item.url for item in narrowed_items), ids, strict=True))
    result = sunday.run_selected_wake(**args)

    assert len(args["wake"].context_refs) == 3
    assert result.lane_classification.lane == WakeLane.BEAUTY
    assert result.lane_classification.confidence == LaneConfidence.HIGH
    assert len(calls["relevance"][1]) == 9
    assert sum(item.relevant for item in calls["bridge"]["relevance_results"]) == 1
    assert tuple(item.candidate_id for item in calls["independence"][0]) == ("news-explicit-opaque",)
    counts = packet.derived_counts
    assert (
        counts.evidence_count,
        counts.timestamped_evidence_count,
        counts.temporal_eligible_count,
        counts.independent_group_count,
        counts.provider_count,
        counts.media,
    ) == (1, 1, 1, 1, 1, ("news",))
    assert assessment.pass_blockers == (
        "INSUFFICIENT_INDEPENDENT_EVIDENCE",
        "INSUFFICIENT_TEMPORAL_EVIDENCE",
    )
    assert assessment.decision == EvidenceDecision.HOLD and assessment.contract_errors == ()


def test_module_has_no_google_rediscovery_clock_environment_or_client_instantiation():
    source = inspect.getsource(sunday)
    assert "collect_google_trends_kr" not in source
    assert "datetime.now" not in source and "datetime.utcnow" not in source
    assert "getenv" not in source and "environ" not in source
    assert "OpenAI(" not in source and "httpx.Client(" not in source
    assert "SourceOrchestrator" not in source
