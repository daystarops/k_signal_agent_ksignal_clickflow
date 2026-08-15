from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from ksignal.engine.evidence import (
    CollectionRun,
    EvidenceLane,
    EvidencePacket,
    EvidenceQuery,
    EvidenceSubject,
    IndependenceStatus,
    SearchWake,
    TimestampStatus,
    structural_pass_blockers,
)
from ksignal.engine.evidence_record_bridge import (
    BRIDGE_COLLECTION_CONTEXT_MISMATCH,
    BRIDGE_INDEPENDENCE_CANDIDATE_ORDER_MISMATCH,
    BRIDGE_INDEPENDENCE_COUNT_MISMATCH,
    BRIDGE_RELEVANCE_CANDIDATE_ORDER_MISMATCH,
    BRIDGE_RELEVANCE_COUNT_MISMATCH,
    DUPLICATE_BRIDGE_COLLECTION_PROVIDER,
    DUPLICATE_BRIDGE_INDEPENDENCE_CANDIDATE_ID,
    DUPLICATE_BRIDGE_RELEVANCE_CANDIDATE_ID,
    DUPLICATE_BRIDGE_SOURCE_CANDIDATE_ID,
    EvidenceCollectionContext,
    NewsisEvidenceSource,
    YouTubeEvidenceSource,
    build_evidence_records,
)
from ksignal.engine.independence_classifier import IndependenceAssignment
from ksignal.engine.relevance_classifier import CandidateRelevance, RelevanceCandidate
from ksignal.engine.source_collectors import NewsisItem, YouTubeItem
from ksignal.engine.models import AccessStatus


UTC = timezone.utc
PUBLISHED = datetime(2026, 8, 14, 14, 18, 35, tzinfo=UTC)
NEWS_DONE = datetime(2026, 8, 14, 15, 55, 7, 987266, tzinfo=UTC)
VIDEO_DONE = datetime(2026, 8, 14, 15, 55, 8, 307100, tzinfo=UTC)


def news_source(candidate_id="newsis:not-derived", *, raw="raw", published=PUBLISHED):
    item = NewsisItem(feed="sports", title="title", description="desc", url="https://news.test/path", published_at=published, published_at_raw=raw)
    candidate = RelevanceCandidate(candidate_id=candidate_id, provider="newsis", source="뉴시스", title=item.title, description=item.description, published_at_raw=item.published_at_raw)
    return NewsisEvidenceSource(candidate=candidate, item=item)


def video_source(video_id="v1", *, channel="channel-1", raw="2026-08-14T15:00:00Z"):
    item = YouTubeItem(video_id=video_id, channel_id=channel, channel_title=f"Channel {video_id}", title=f"Title {video_id}", description=f"Desc {video_id}", published_at=PUBLISHED, published_at_raw=raw, url=f"https://youtube.test/{video_id}")
    candidate = RelevanceCandidate(candidate_id=f"youtube:{video_id}", provider="youtube", source=item.channel_title, title=item.title, description=item.description, published_at_raw=item.published_at_raw)
    return YouTubeEvidenceSource(candidate=candidate, item=item)


def relevance(source, relevant=True):
    return CandidateRelevance(candidate_id=source.candidate.candidate_id, relevant=relevant, confidence="high", matched_subject="subject", reason="fixture")


def assignment(source, status="independent", *, duplicate=None, group="unusual:group:!", counts=None):
    if counts is None:
        counts = status == "independent"
    candidate_id = source.candidate.candidate_id
    return IndependenceAssignment(candidate_id=candidate_id, duplicate_group_id=duplicate or f"duplicate:{candidate_id}", independence_group_id=group, independence_status=status, counts_toward_independence=counts, reason="fixture")


def context(provider):
    return EvidenceCollectionContext(provider=provider, run_id=f"run-{provider}", completed_at=NEWS_DONE if provider == "newsis" else VIDEO_DONE)


def build(sources, rels=None, assignments=None, contexts=None):
    rels = tuple(relevance(s) for s in sources) if rels is None else rels
    assignments = tuple(assignment(s) for s, r in zip(sources, rels) if r.relevant) if assignments is None else assignments
    contexts = tuple(context(p) for p in dict.fromkeys(s.candidate.provider for s in sources)) if contexts is None else contexts
    return build_evidence_records(sources=sources, relevance_results=rels, independence_assignments=assignments, collection_contexts=contexts)


@pytest.mark.parametrize("factory", [news_source, video_source])
def test_source_wrappers_are_strict_and_frozen(factory):
    source = factory()
    with pytest.raises(ValidationError):
        source.candidate = source.candidate
    with pytest.raises(ValidationError):
        type(source)(**source.model_dump(), extra=True)


def test_collection_context_is_strict_frozen_nonempty_and_aware():
    value = context("newsis")
    with pytest.raises(ValidationError):
        value.run_id = "changed"
    with pytest.raises(ValidationError):
        EvidenceCollectionContext(**value.model_dump(), extra=True)
    with pytest.raises(ValidationError, match="run_id"):
        EvidenceCollectionContext(provider="newsis", run_id=" ", completed_at=NEWS_DONE)
    with pytest.raises(ValidationError, match="timezone-aware"):
        EvidenceCollectionContext(provider="newsis", run_id="run", completed_at=datetime(2026, 1, 1))


@pytest.mark.parametrize("field,value", [("provider", "youtube"), ("source", "other"), ("title", "other"), ("description", "other"), ("published_at_raw", "other")])
def test_newsis_wrapper_rejects_correlation_disagreement(field, value):
    source = news_source()
    candidate = source.candidate.model_copy(update={field: value})
    with pytest.raises(ValidationError):
        NewsisEvidenceSource(candidate=candidate, item=source.item)


def test_newsis_id_need_not_be_derived_from_url():
    assert news_source("opaque-correlation-id").candidate.candidate_id == "opaque-correlation-id"


@pytest.mark.parametrize("field,value", [("provider", "newsis"), ("candidate_id", "wrong"), ("source", "other"), ("title", "other"), ("description", "other"), ("published_at_raw", "other")])
def test_youtube_wrapper_rejects_correlation_disagreement(field, value):
    source = video_source()
    candidate = source.candidate.model_copy(update={field: value})
    with pytest.raises(ValidationError):
        YouTubeEvidenceSource(candidate=candidate, item=source.item)


@pytest.mark.parametrize("which,error", [("source", DUPLICATE_BRIDGE_SOURCE_CANDIDATE_ID), ("relevance", DUPLICATE_BRIDGE_RELEVANCE_CANDIDATE_ID), ("independence", DUPLICATE_BRIDGE_INDEPENDENCE_CANDIDATE_ID), ("context", DUPLICATE_BRIDGE_COLLECTION_PROVIDER)])
def test_duplicate_relational_ids_fail(which, error):
    source = news_source()
    kwargs = dict(sources=(source,), relevance_results=(relevance(source),), independence_assignments=(assignment(source),), collection_contexts=(context("newsis"),))
    key = {"source": "sources", "relevance": "relevance_results", "independence": "independence_assignments", "context": "collection_contexts"}[which]
    kwargs[key] = kwargs[key] * 2
    with pytest.raises(ValueError, match=error):
        build_evidence_records(**kwargs)


def test_relevance_count_and_order_fail_without_repair():
    sources = (news_source("a"), news_source("b"))
    with pytest.raises(ValueError, match=BRIDGE_RELEVANCE_COUNT_MISMATCH):
        build(sources, rels=(relevance(sources[0]),))
    with pytest.raises(ValueError, match=BRIDGE_RELEVANCE_CANDIDATE_ORDER_MISMATCH):
        build(sources, rels=tuple(relevance(s) for s in reversed(sources)))


def test_independence_count_order_and_irrelevant_assignment_fail():
    sources = (news_source("a"), news_source("b"))
    rels = (relevance(sources[0]), relevance(sources[1]))
    with pytest.raises(ValueError, match=BRIDGE_INDEPENDENCE_COUNT_MISMATCH):
        build(sources, rels=rels, assignments=(assignment(sources[0]),))
    with pytest.raises(ValueError, match=BRIDGE_INDEPENDENCE_CANDIDATE_ORDER_MISMATCH):
        build(sources, rels=rels, assignments=(assignment(sources[1]), assignment(sources[0])))
    rels = (relevance(sources[0], False), relevance(sources[1]))
    with pytest.raises(ValueError, match=BRIDGE_INDEPENDENCE_COUNT_MISMATCH):
        build(sources, rels=rels, assignments=(assignment(sources[0]), assignment(sources[1])))


def test_collection_context_exactness_and_empty_input():
    source = news_source()
    with pytest.raises(ValueError, match=BRIDGE_COLLECTION_CONTEXT_MISMATCH):
        build((source,), contexts=())
    with pytest.raises(ValueError, match=BRIDGE_COLLECTION_CONTEXT_MISMATCH):
        build((source,), contexts=(context("newsis"), context("youtube")))
    assert build_evidence_records(sources=(), relevance_results=(), independence_assignments=(), collection_contexts=()) == ()


def test_irrelevant_is_omitted_without_assignment_and_order_is_preserved():
    sources = (video_source("a"), video_source("b"), video_source("c"))
    rels = (relevance(sources[0]), relevance(sources[1], False), relevance(sources[2]))
    records = build(sources, rels=rels, assignments=(assignment(sources[0]), assignment(sources[2])))
    assert [r.evidence_id for r in records] == ["youtube:a", "youtube:c"]


@pytest.mark.parametrize("raw,published,status,eligible", [("raw", PUBLISHED, TimestampStatus.RELIABLE, True), ("malformed definitely not parsed", None, TimestampStatus.AMBIGUOUS, False), ("", None, TimestampStatus.MISSING, False)])
def test_newsis_exact_mapping_timestamp_and_no_provider_id(raw, published, status, eligible):
    source = news_source("newsis:NISX20260814_0003750360", raw=raw, published=published)
    source = source.model_copy(update={"item": source.item.model_copy(update={"url": "https://newsis.com/view/NISX20260814_0003750360"})})
    record = build((source,))[0]
    assert (record.provider, record.medium, record.provider_item_id) == ("newsis", "news", None)
    assert (record.source_name, record.source_identity) == ("뉴시스", "newsis:publisher")
    assert (record.url, record.title, record.excerpt) == (source.item.url, source.item.title, source.item.description)
    assert record.published_at is published and record.published_at_raw == raw
    assert (record.timestamp_status, record.temporal_eligible) == (status, eligible)
    assert record.first_seen_at == NEWS_DONE and record.first_seen_at != record.published_at


def test_youtube_exact_mapping_and_context_time():
    source = video_source()
    record = build((source,))[0]
    assert (record.provider, record.medium, record.provider_item_id) == ("youtube", "video", "v1")
    assert (record.source_name, record.source_identity) == (source.item.channel_title, source.item.channel_id)
    assert (record.url, record.title, record.excerpt) == (source.item.url, source.item.title, source.item.description)
    assert (record.published_at, record.published_at_raw) == (source.item.published_at, source.item.published_at_raw)
    assert (record.timestamp_status, record.temporal_eligible) == (TimestampStatus.RELIABLE, True)
    assert record.first_seen_at == VIDEO_DONE


@pytest.mark.parametrize("status,counts", [("duplicate", False), ("uncertain", False), ("syndicated", False), ("independent", True)])
def test_assignment_fields_are_copied_and_all_statuses_produce_records(status, counts):
    source = video_source()
    assigned = assignment(source, status, duplicate="odd duplicate !", group="odd group !", counts=counts)
    record = build((source,), assignments=(assigned,))[0]
    assert (record.duplicate_group_id, record.independence_group_id) == ("odd duplicate !", "odd group !")
    assert (record.independence_status, record.counts_toward_independence) == (IndependenceStatus(status), counts)


def test_no_neighbor_calls_clients_network_or_collection_run(monkeypatch):
    import ksignal.engine.independence_classifier as independence
    import ksignal.engine.relevance_classifier as relevance_module
    import ksignal.engine.source_collectors as collectors
    def forbidden(*args, **kwargs):
        raise AssertionError("forbidden dependency invoked")
    monkeypatch.setattr(relevance_module, "classify_candidate_relevance", forbidden)
    monkeypatch.setattr(independence, "classify_candidate_independence", forbidden)
    for name in ("collect_newsis_pool", "collect_youtube_search", "collect_google_trends_kr"):
        monkeypatch.setattr(collectors, name, forbidden)
    records = build((news_source(),))
    assert len(records) == 1
    assert all(type(record).__name__ == "EvidenceRecord" for record in records)


def test_real_im_ji_min_bridge_regression_preserves_current_doctrine():
    injury = news_source("newsis:NISX20260814_0003750360")
    injury = NewsisEvidenceSource(
        candidate=injury.candidate.model_copy(update={
            "title": "강습 타구에 얼굴 강타당한 NC 임지민, 구급차로 병원 이송",
            "description": "임지민 부상 기사",
        }),
        item=injury.item.model_copy(update={
            "title": "강습 타구에 얼굴 강타당한 NC 임지민, 구급차로 병원 이송",
            "description": "임지민 부상 기사",
        }),
    )
    roundup = news_source("newsis:NISX20260814_0003750254")
    video_specs = (
        ("0lFRsI7OvVk", "UCXg-Wm1bN4PhQRb86SHb38A", "uncertain"),
        ("j9EEd9SQMxY", "UCcLWiDZ_EYig1r83dIbWW1Q", "uncertain"),
        ("iosYCnw5HaY", "UCHKym-ieOtI77k3FpbzvtsQ", "uncertain"),
        ("xq8eOiiucBI", "UCnDxhSF3ooyUjQJIpBfyKGQ", "uncertain"),
        ("dlvgSpzutK4", "UCgoTsLlWiQDvWRgmMQJ5-7g", "syndicated"),
    )
    videos = tuple(video_source(video_id, channel=channel) for video_id, channel, _ in video_specs)
    sources = (roundup, injury, *videos)
    rels = (relevance(roundup, False), relevance(injury), *(relevance(item) for item in videos))
    assignments = (
        assignment(injury, group="newsis:publisher"),
        *(assignment(item, status, group=f"youtube:channel:{item.item.channel_id}") for item, (_, _, status) in zip(videos, video_specs)),
    )
    records = build(sources, rels=rels, assignments=assignments)

    assert len(records) == 6
    assert records[0].provider_item_id is None
    assert [record.counts_toward_independence for record in records] == [True, False, False, False, False, False]

    runs = (
        CollectionRun(run_id=records[0].run_id, provider="newsis", operation="rss", status=AccessStatus.CAPTURED, started_at=NEWS_DONE, completed_at=NEWS_DONE, raw_item_count=2, relevant_item_count=1),
        CollectionRun(run_id=records[1].run_id, provider="youtube", operation="search", status=AccessStatus.CAPTURED, started_at=VIDEO_DONE, completed_at=VIDEO_DONE, raw_item_count=5, relevant_item_count=5),
    )
    packet = EvidencePacket(
        schema_version="evidence_packet.v0.1",
        packet_id="packet-im-ji-min",
        packet_revision=1,
        issue_id="issue-im-ji-min",
        candidate_id="candidate-im-ji-min",
        lane=EvidenceLane.SPORTS,
        subject=EvidenceSubject(label="임지민"),
        query=EvidenceQuery(original="임지민", normalized="임지민"),
        search_wake=SearchWake(provider="google_trends_rss", geo="KR", observed_at=NEWS_DONE, approx_traffic_raw="1000+", approx_traffic_floor=1000),
        collection_runs=runs,
        evidence=records,
        packet_created_at=VIDEO_DONE,
    )
    counts = packet.derived_counts
    assert (counts.evidence_count, counts.timestamped_evidence_count, counts.temporal_eligible_count, counts.independent_group_count) == (6, 6, 6, 1)
    assert counts.provider_count == 2
    assert counts.media == ("news", "video")
    assert structural_pass_blockers(packet) == ("INSUFFICIENT_INDEPENDENT_EVIDENCE", "INSUFFICIENT_TEMPORAL_EVIDENCE")
