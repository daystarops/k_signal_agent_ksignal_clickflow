from __future__ import annotations

import unicodedata
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from ksignal.engine.evidence import (
    EvidenceLane,
    EvidenceQuery,
    EvidenceRecord,
    EvidenceSubject,
    IndependenceStatus,
    TimestampStatus,
    structural_pass_blockers,
)
from ksignal.engine.evidence_packet_assembly import (
    OUT_OF_SCOPE_WAKE_CANNOT_BUILD_PACKET,
    PACKET_QUERY_WAKE_MISMATCH,
    WAKE_LANE_QUERY_MISMATCH,
    assemble_evidence_packet,
)
from ksignal.engine.models import AccessStatus
from ksignal.engine.source_collectors import (
    GoogleContextRef,
    GoogleWakeCandidate,
    NewsisCollection,
    NewsisItem,
    YouTubeCollection,
    YouTubeItem,
)
from ksignal.engine.wake_classifier import LaneConfidence, WakeLane, WakeLaneClassification


UTC = timezone.utc
OBSERVED = datetime(2026, 8, 14, 14, tzinfo=UTC)
NEWS_START = OBSERVED + timedelta(minutes=1)
NEWS_DONE = OBSERVED + timedelta(minutes=2)
VIDEO_START = OBSERVED + timedelta(minutes=3)
VIDEO_DONE = OBSERVED + timedelta(minutes=4)
CREATED = datetime(2037, 1, 2, 3, 4, 5, 678901, tzinfo=UTC)


def news_item(index: int = 0) -> NewsisItem:
    return NewsisItem(feed="sports", title=f"News {index}", description=f"Body {index}",
                      url=f"https://news.test/{index}", published_at=NEWS_DONE,
                      published_at_raw="Fri, 14 Aug 2026 14:02:00 +0000")


def youtube_item(index: int = 0) -> YouTubeItem:
    return YouTubeItem(video_id=f"v{index}", channel_id=f"channel-{index}",
                       channel_title=f"Channel {index}", title=f"Video {index}",
                       description=f"Body {index}", published_at=VIDEO_DONE,
                       published_at_raw="2026-08-14T14:04:00Z",
                       url=f"https://youtube.test/watch?v=v{index}")


def record(provider: str, index: int = 0, *, status=IndependenceStatus.INDEPENDENT,
           counts=True) -> EvidenceRecord:
    is_news = provider == "newsis"
    return EvidenceRecord(
        evidence_id=f"{provider}-{index}", run_id=f"{provider}-run", provider=provider,
        medium="news" if is_news else "video", provider_item_id=None if is_news else f"v{index}",
        source_name="Newsis" if is_news else f"Channel {index}",
        source_identity="newsis:publisher" if is_news else f"channel-{index}",
        url=f"https://{provider}.test/{index}", title=f"Title {index}", excerpt=f"Excerpt {index}",
        published_at=NEWS_DONE, published_at_raw="raw", first_seen_at=VIDEO_DONE,
        timestamp_status=TimestampStatus.RELIABLE, temporal_eligible=True,
        duplicate_group_id=f"duplicate-{provider}-{index}",
        independence_group_id="newsis:publisher" if is_news else f"channel-{index}",
        independence_status=status, counts_toward_independence=counts,
    )


def inputs(*, lane=WakeLane.SPORTS, wake_query="임지민", query_original=None,
           lane_query=None, evidence=(), news_count=2, video_count=5, contexts=()):
    wake = GoogleWakeCandidate(query=wake_query, observed_at=OBSERVED,
                               approx_traffic_raw="1000+", approx_traffic_floor=1000,
                               context_refs=tuple(contexts))
    return dict(
        packet_id="packet-owned", packet_revision=7, issue_id="issue-owned",
        candidate_id="candidate-owned", packet_created_at=CREATED,
        subject=EvidenceSubject(label="임지민", aliases=("alias",)),
        query=EvidenceQuery(original=wake_query if query_original is None else query_original,
                            normalized="CALLER NORMALIZED"), wake=wake,
        lane_classification=WakeLaneClassification(
            query=wake_query if lane_query is None else lane_query, lane=lane,
            confidence=LaneConfidence.LOW, reason="fixture"),
        newsis_collection=NewsisCollection(started_at=NEWS_START, completed_at=NEWS_DONE,
                                           items=tuple(news_item(i) for i in range(news_count))),
        youtube_collection=YouTubeCollection(started_at=VIDEO_START, completed_at=VIDEO_DONE,
                                             items=tuple(youtube_item(i) for i in range(video_count))),
        newsis_run_id="newsis-run", youtube_run_id="youtube-run", evidence=evidence,
    )


@pytest.mark.parametrize("wake_lane", [WakeLane.BEAUTY, WakeLane.FOOD, WakeLane.SOCIETY,
                                        WakeLane.FANDOM, WakeLane.SPORTS])
def test_all_in_scope_lanes_map_by_exact_value(wake_lane):
    packet = assemble_evidence_packet(**inputs(lane=wake_lane))
    assert packet.lane == EvidenceLane(wake_lane.value)


def test_out_of_scope_hard_fails():
    with pytest.raises(ValueError, match=OUT_OF_SCOPE_WAKE_CANNOT_BUILD_PACKET):
        assemble_evidence_packet(**inputs(lane=WakeLane.OUT_OF_SCOPE))


def test_lane_query_mismatch_hard_fails():
    with pytest.raises(ValueError, match=WAKE_LANE_QUERY_MISMATCH):
        assemble_evidence_packet(**inputs(lane_query="different"))


@pytest.mark.parametrize(
    ("mismatch_class", "wake_query", "different"),
    [
        ("capitalization", "임지민", "IM JI-MIN"),
        ("whitespace", "임지민", " 임지민"),
        ("unicode normalization", "임지민", unicodedata.normalize("NFD", "임지민")),
    ],
)
def test_packet_query_matching_is_exact(mismatch_class, wake_query, different):
    if mismatch_class == "unicode normalization":
        assert different != wake_query
    with pytest.raises(ValueError, match=PACKET_QUERY_WAKE_MISMATCH):
        assemble_evidence_packet(**inputs(wake_query=wake_query, query_original=different))


def test_mechanical_wake_context_run_identity_and_caller_fields_mapping():
    contexts = (GoogleContextRef(title="second", source="B", url="https://b"),
                GoogleContextRef(title="first", source="A", url="https://a"))
    values = inputs(contexts=contexts)
    packet = assemble_evidence_packet(**values)
    assert packet.search_wake.model_dump() == {
        "provider": "google_trends_rss", "geo": "KR", "observed_at": OBSERVED,
        "approx_traffic_raw": "1000+", "approx_traffic_floor": 1000,
        "context_refs": tuple({"title": x.title, "source": x.source, "url": x.url} for x in contexts),
    }
    assert (packet.packet_id, packet.packet_revision, packet.issue_id, packet.candidate_id) == (
        "packet-owned", 7, "issue-owned", "candidate-owned")
    assert packet.packet_created_at == CREATED
    assert packet.subject is values["subject"] and packet.query is values["query"]
    assert packet.query.normalized == "CALLER NORMALIZED"
    news, video = packet.collection_runs
    assert news.model_dump() == dict(run_id="newsis-run", provider="newsis",
        operation="collect_newsis_pool", status=AccessStatus.CAPTURED, failure_mode=None,
        started_at=NEWS_START, completed_at=NEWS_DONE, raw_item_count=2, relevant_item_count=0)
    assert video.model_dump() == dict(run_id="youtube-run", provider="youtube",
        operation="collect_youtube_search", status=AccessStatus.CAPTURED, failure_mode=None,
        started_at=VIDEO_START, completed_at=VIDEO_DONE, raw_item_count=5, relevant_item_count=0)
    assert news.provider != "newsis_rss" and video.provider != "youtube_data_api"


def test_empty_context_and_evidence_and_structural_blockers():
    packet = assemble_evidence_packet(**inputs())
    assert packet.search_wake.context_refs == () and packet.evidence == ()
    assert [run.relevant_item_count for run in packet.collection_runs] == [0, 0]
    assert structural_pass_blockers(packet) == (
        "NO_RELEVANT_DOWNSTREAM_EVIDENCE", "INSUFFICIENT_INDEPENDENT_EVIDENCE",
        "INSUFFICIENT_TEMPORAL_EVIDENCE")


def test_evidence_order_and_provider_counts_include_nonindependent_records():
    evidence = (record("youtube", 1, status=IndependenceStatus.UNCERTAIN, counts=False),
                record("newsis", 1, status=IndependenceStatus.DUPLICATE, counts=False),
                record("youtube", 2, status=IndependenceStatus.SYNDICATED, counts=False))
    packet = assemble_evidence_packet(**inputs(evidence=evidence))
    assert packet.evidence == evidence
    assert [run.relevant_item_count for run in packet.collection_runs] == [1, 2]


def test_full_newsis_pool_raw_count_is_not_evidence_count():
    packet = assemble_evidence_packet(**inputs(news_count=7, evidence=(record("newsis"),)))
    assert (packet.collection_runs[0].raw_item_count,
            packet.collection_runs[0].relevant_item_count) == (7, 1)


def test_existing_packet_validation_owns_link_errors():
    duplicate_runs = inputs()
    duplicate_runs["youtube_run_id"] = "newsis-run"
    with pytest.raises(ValidationError, match="run_id values must be unique"):
        assemble_evidence_packet(**duplicate_runs)
    with pytest.raises(ValidationError, match="must reference a collection run"):
        assemble_evidence_packet(**inputs(evidence=(record("newsis").model_copy(update={"run_id": "unknown"}),)))
    wrong = record("newsis").model_copy(update={"provider": "youtube"})
    with pytest.raises(ValidationError, match="provider must match"):
        assemble_evidence_packet(**inputs(evidence=(wrong,)))


def test_search_wake_validation_remains_active():
    values = inputs()
    values["wake"] = values["wake"].model_copy(update={"approx_traffic_floor": 999})
    with pytest.raises(ValidationError, match="must match approx_traffic_raw"):
        assemble_evidence_packet(**values)


def test_derived_counts_are_model_computed_and_not_manufactured():
    packet = assemble_evidence_packet(**inputs())
    assert "derived_counts" not in packet.__class__.model_fields
    assert packet.derived_counts.evidence_count == 0


def test_no_neighbor_calls_clients_environment_or_clock_and_inputs_unchanged(monkeypatch):
    import ksignal.engine.candidate_preparation as preparation
    import ksignal.engine.evidence as evidence_module
    import ksignal.engine.evidence_record_bridge as bridge
    import ksignal.engine.independence_classifier as independence
    import ksignal.engine.newsis_candidate_narrowing as narrowing
    import ksignal.engine.relevance_classifier as relevance
    import ksignal.engine.source_collectors as collectors
    import ksignal.engine.wake_classifier as wake_classifier

    def forbidden(*args, **kwargs):
        raise AssertionError("forbidden dependency invoked")

    for module, names in ((collectors, ("collect_google_trends_kr", "collect_newsis_pool", "collect_youtube_search")),
                          (wake_classifier, ("classify_wake_lanes",)),
                          (narrowing, ("narrow_newsis_candidates",)),
                          (preparation, ("prepare_newsis_candidates", "prepare_youtube_candidates")),
                          (relevance, ("classify_candidate_relevance",)),
                          (independence, ("classify_candidate_independence",)),
                          (bridge, ("build_evidence_records",)),
                          (evidence_module, ("structural_pass_blockers",))):
        for name in names:
            monkeypatch.setattr(module, name, forbidden)
    values = inputs()
    before = {key: value.model_dump() for key, value in values.items() if hasattr(value, "model_dump")}
    packet = assemble_evidence_packet(**values)
    after = {key: value.model_dump() for key, value in values.items() if hasattr(value, "model_dump")}
    assert before == after and packet.packet_created_at == CREATED


def test_real_im_ji_min_regression_remains_structurally_hold_blocked():
    records = [record("newsis", 0)]
    records.extend(record("youtube", i, status=IndependenceStatus.UNCERTAIN, counts=False)
                   for i in range(4))
    records.append(record("youtube", 4, status=IndependenceStatus.SYNDICATED, counts=False))
    values = inputs(evidence=tuple(records))
    values.update(packet_id="issue002-imjimin-packet-r1", packet_revision=1,
                  issue_id="issue002", candidate_id="imjimin",
                  query=EvidenceQuery(original="임지민", normalized="임지민"),
                  newsis_run_id="issue002-imjimin-newsis-r1",
                  youtube_run_id="issue002-imjimin-youtube-r1")
    records[0] = records[0].model_copy(update={"run_id": values["newsis_run_id"]})
    for index in range(1, 6):
        records[index] = records[index].model_copy(update={"run_id": values["youtube_run_id"]})
    values["evidence"] = tuple(records)
    packet = assemble_evidence_packet(**values)
    counts = packet.derived_counts
    assert values["wake"].query == "임지민"
    assert packet.subject.label == "임지민"
    assert packet.query.original == "임지민"
    assert (counts.evidence_count, counts.timestamped_evidence_count,
            counts.temporal_eligible_count, counts.independent_group_count,
            counts.provider_count, counts.media) == (6, 6, 6, 1, 2, ("news", "video"))
    assert [(run.raw_item_count, run.relevant_item_count) for run in packet.collection_runs] == [(2, 1), (5, 5)]
    assert structural_pass_blockers(packet) == (
        "INSUFFICIENT_INDEPENDENT_EVIDENCE", "INSUFFICIENT_TEMPORAL_EVIDENCE")
