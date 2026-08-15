from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from ksignal.engine.candidate_preparation import (
    DUPLICATE_NEWSIS_BINDING_CANDIDATE_ID,
    DUPLICATE_NEWSIS_BINDING_URL,
    DUPLICATE_YOUTUBE_CANDIDATE_ID,
    NEWSIS_SOURCE_URL_AMBIGUOUS,
    NEWSIS_SOURCE_URL_NOT_FOUND,
    NewsisCandidateBinding,
    PreparedCandidate,
    prepare_newsis_candidates,
    prepare_youtube_candidates,
)
from ksignal.engine.independence_classifier import IndependenceCandidate
from ksignal.engine.newsis_candidate_narrowing import NewsisNarrowedCandidate
from ksignal.engine.relevance_classifier import RelevanceCandidate
from ksignal.engine.source_collectors import (
    NewsisCollection,
    NewsisItem,
    YouTubeCollection,
    YouTubeItem,
)


UTC = timezone.utc
NOW = datetime(2026, 8, 14, 14, 18, 35, tzinfo=UTC)


def news_item(url="https://news.test/article", **updates):
    values = dict(feed="sports", title="original title", description="original description",
                  url=url, published_at=NOW, published_at_raw="original raw")
    values.update(updates)
    return NewsisItem(**values)


def narrowed(url="https://news.test/article", **updates):
    values = dict(url=url, feeds=("sports",), title="narrowed title",
                  description="narrowed description", published_at_raw="narrowed raw",
                  literal_match=False, semantic_score=0.5, selected_by="semantic")
    values.update(updates)
    return NewsisNarrowedCandidate(**values)


def binding(candidate_id="opaque-id", url="https://news.test/article"):
    return NewsisCandidateBinding(candidate_id=candidate_id, narrowed=narrowed(url))


def news_collection(*items):
    return NewsisCollection(started_at=NOW, completed_at=NOW, items=tuple(items))


def youtube_item(video_id="v1", **updates):
    values = dict(video_id=video_id, channel_id=f"channel-{video_id}",
                  channel_title=f"Channel {video_id}", title=f"Title {video_id}",
                  description=f"Description {video_id}", published_at=NOW,
                  published_at_raw="2026-08-14T14:18:35Z",
                  url=f"https://youtube.test/watch?v={video_id}")
    values.update(updates)
    return YouTubeItem(**values)


def youtube_collection(*items):
    return YouTubeCollection(started_at=NOW, completed_at=NOW, items=tuple(items))


def prepared_news(candidate_id="opaque-id", item=None, narrow=None):
    item = item or news_item()
    narrow = narrow or narrowed(item.url)
    return prepare_newsis_candidates(
        bindings=(NewsisCandidateBinding(candidate_id=candidate_id, narrowed=narrow),),
        collection=news_collection(item),
    )[0]


def test_binding_is_strict_frozen_nonempty_and_preserves_opaque_id():
    value = binding("caller-owned-newsis-id-123")
    assert value.candidate_id == "caller-owned-newsis-id-123"
    with pytest.raises(ValidationError):
        value.candidate_id = "changed"
    with pytest.raises(ValidationError):
        NewsisCandidateBinding(**value.model_dump(), extra=True)
    with pytest.raises(ValidationError, match="candidate_id"):
        binding("  ")


def test_prepared_is_strict_frozen_and_rejects_correlation_mismatches():
    value = prepared_news()
    with pytest.raises(ValidationError):
        value.source = value.source
    with pytest.raises(ValidationError):
        PreparedCandidate(**value.model_dump(), extra=True)
    wrong_id = value.independence_candidate.model_copy(update={"candidate_id": "wrong"})
    with pytest.raises(ValidationError, match="IDs must match"):
        PreparedCandidate(source=value.source, independence_candidate=wrong_id)
    wrong_provider = value.independence_candidate.model_copy(update={"provider": "youtube"})
    with pytest.raises(ValidationError, match="providers must match"):
        PreparedCandidate(source=value.source, independence_candidate=wrong_provider)


def test_empty_collections_return_empty_tuples():
    assert prepare_newsis_candidates(bindings=(), collection=news_collection()) == ()
    assert prepare_youtube_candidates(collection=youtube_collection()) == ()


@pytest.mark.parametrize(
    ("bindings", "error"),
    [
        ((binding("same", "https://n/1"), binding("same", "https://n/2")),
         DUPLICATE_NEWSIS_BINDING_CANDIDATE_ID),
        ((binding("one", "https://n/1"), binding("two", "https://n/1")),
         DUPLICATE_NEWSIS_BINDING_URL),
    ],
)
def test_newsis_binding_ids_and_urls_must_be_unique(bindings, error):
    with pytest.raises(ValueError, match=error):
        prepare_newsis_candidates(bindings=bindings, collection=news_collection())


def test_newsis_exact_url_cardinality_and_no_normalization():
    exact = "https://news.test/article?x=1"
    with pytest.raises(ValueError, match=NEWSIS_SOURCE_URL_NOT_FOUND):
        prepare_newsis_candidates(bindings=(binding(url=exact + "&y=2"),),
                                  collection=news_collection(news_item(exact)))
    with pytest.raises(ValueError, match=NEWSIS_SOURCE_URL_NOT_FOUND):
        prepare_newsis_candidates(bindings=(binding(url="HTTPS://news.test/article?x=1"),),
                                  collection=news_collection(news_item(exact)))
    with pytest.raises(ValueError, match=NEWSIS_SOURCE_URL_AMBIGUOUS):
        prepare_newsis_candidates(bindings=(binding(url=exact),),
                                  collection=news_collection(news_item(exact), news_item(exact)))


def test_newsis_maps_original_item_metadata_and_correlation_exactly():
    original = news_item(title="collector title", description="collector description",
                         published_at_raw="collector raw")
    value = prepared_news("opaque-caller-id", original, narrowed(original.url))
    candidate = value.source.candidate
    independent = value.independence_candidate
    assert (candidate.candidate_id, candidate.provider, candidate.source) == (
        "opaque-caller-id", "newsis", "뉴시스")
    assert (candidate.title, candidate.description, candidate.published_at_raw) == (
        original.title, original.description, original.published_at_raw)
    assert value.source.item == original and value.source.item.published_at == NOW
    assert independent.model_dump() == {
        "candidate_id": "opaque-caller-id", "provider": "newsis", "source_name": "뉴시스",
        "source_identity": "newsis:publisher", "provider_item_id": None, "url": original.url,
        "title": original.title, "description": original.description,
    }
    assert (candidate.candidate_id, candidate.provider) == (
        independent.candidate_id, independent.provider)


def test_newsis_preserves_binding_order():
    items = (news_item("https://n/1"), news_item("https://n/2"))
    result = prepare_newsis_candidates(
        bindings=(binding("second", items[1].url), binding("first", items[0].url)),
        collection=news_collection(*items),
    )
    assert [value.source.candidate.candidate_id for value in result] == ["second", "first"]


def test_real_im_ji_min_exact_join_and_caller_owned_ids():
    url = "https://www.newsis.com/view/NISX20260814_0003750360"
    original = news_item(
        url, title="강습 타구에 얼굴 강타당한 NC 임지민, 구급차로 병원 이송",
        description="NC 투수 임지민이 경기 중 강습 타구에 맞아 병원으로 이송됐다.",
        published_at_raw="Fri, 14 Aug 2026 23:18:35 +0900",
    )
    different = narrowed(url, description="<p>다른 마크업 표현</p>")
    for supplied_id in ("newsis:NISX20260814_0003750360", "caller-owned-opaque-id"):
        result = prepare_newsis_candidates(
            bindings=(NewsisCandidateBinding(candidate_id=supplied_id, narrowed=different),),
            collection=news_collection(original),
        )
        assert len(result) == 1
        value = result[0]
        assert value.source.candidate.candidate_id == supplied_id
        assert value.source.item.url == url and value.source.item.published_at == NOW
        assert value.source.candidate.description == original.description
        assert value.independence_candidate.provider_item_id is None
        assert value.independence_candidate.source_identity == "newsis:publisher"


def test_youtube_exact_mapping_order_and_shared_correlation():
    items = (youtube_item("b"), youtube_item("a"))
    result = prepare_youtube_candidates(collection=youtube_collection(*items))
    assert [value.source.candidate.candidate_id for value in result] == ["youtube:b", "youtube:a"]
    for value, item in zip(result, items):
        candidate = value.source.candidate
        independent = value.independence_candidate
        assert value.source.item == item
        assert candidate.model_dump() == {
            "candidate_id": f"youtube:{item.video_id}", "provider": "youtube",
            "source": item.channel_title, "title": item.title,
            "description": item.description, "published_at_raw": item.published_at_raw,
        }
        assert independent.model_dump() == {
            "candidate_id": f"youtube:{item.video_id}", "provider": "youtube",
            "source_name": item.channel_title, "source_identity": item.channel_id,
            "provider_item_id": item.video_id, "url": item.url,
            "title": item.title, "description": item.description,
        }
        assert (candidate.candidate_id, candidate.provider) == (
            independent.candidate_id, independent.provider)


def test_duplicate_youtube_candidate_ids_fail():
    with pytest.raises(ValueError, match=DUPLICATE_YOUTUBE_CANDIDATE_ID):
        prepare_youtube_candidates(collection=youtube_collection(youtube_item("same"),
                                                                  youtube_item("same")))


def test_preparation_invokes_no_neighbors_clients_embeddings_or_current_time(monkeypatch):
    import ksignal.engine.evidence_record_bridge as bridge
    import ksignal.engine.independence_classifier as independence
    import ksignal.engine.newsis_candidate_narrowing as narrowing
    import ksignal.engine.relevance_classifier as relevance
    import ksignal.engine.source_collectors as collectors

    def forbidden(*args, **kwargs):
        raise AssertionError("forbidden dependency invoked")

    for module, names in (
        (collectors, ("collect_newsis_pool", "collect_youtube_search")),
        (narrowing, ("narrow_newsis_candidates",)),
        (relevance, ("classify_candidate_relevance",)),
        (independence, ("classify_candidate_independence",)),
        (bridge, ("build_evidence_records",)),
    ):
        for name in names:
            monkeypatch.setattr(module, name, forbidden)
    assert prepared_news().source.candidate.candidate_id == "opaque-id"
    assert prepare_youtube_candidates(collection=youtube_collection(youtube_item()))
    # No client, embeddings object, clock value, environment, or API credential is supplied.
