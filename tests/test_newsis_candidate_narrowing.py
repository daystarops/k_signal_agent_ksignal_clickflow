from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from ksignal.engine.newsis_candidate_narrowing import (
    DEFAULT_NEWSIS_NARROWING_MODEL,
    NEWSIS_MAX_CANDIDATES,
    NewsisCandidateNarrowingBatch,
    NewsisCandidateSelection,
    NewsisNarrowedCandidate,
    NewsisWakeNarrowingResult,
    narrow_newsis_candidates,
)
from ksignal.engine.source_collectors import GoogleContextRef, GoogleWakeCandidate, NewsisItem


class FakeEmbeddings:
    def __init__(self, vectors, *, model="actual-embedding-model", error=None):
        self.vectors = vectors
        self.model = model
        self.error = error
        self.calls = []
        self.call_completed_at = None

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        self.call_completed_at = datetime.now(timezone.utc)
        return SimpleNamespace(
            data=[SimpleNamespace(embedding=vector) for vector in self.vectors],
            model=self.model,
        )


def client(vectors, **kwargs):
    return SimpleNamespace(embeddings=FakeEmbeddings(vectors, **kwargs))


def wake(query="임지민", contexts=()):
    return GoogleWakeCandidate(
        query=query,
        observed_at=datetime(2099, 1, 2, tzinfo=timezone.utc),
        approx_traffic_raw="SENTINEL_TRAFFIC",
        approx_traffic_floor=987654,
        context_refs=contexts,
    )


def item(number, title, description="설명", feed="sports", url=None):
    return NewsisItem(
        feed=feed,
        title=title,
        description=description,
        url=url or f"https://newsis.test/{number}",
        published_at=None,
        published_at_raw=f"published-{number}",
    )


def test_strict_frozen_contracts_and_default_model():
    assert DEFAULT_NEWSIS_NARROWING_MODEL == "text-embedding-3-small"
    candidate = NewsisNarrowedCandidate(
        url="u", feeds=("sports",), title="t", description="d", published_at_raw="p",
        literal_match=False, semantic_score=0.5, selected_by="semantic",
    )
    with pytest.raises(ValidationError):
        candidate.title = "changed"
    with pytest.raises(ValidationError):
        NewsisNarrowedCandidate(**candidate.model_dump(), extra_field=True)
    with pytest.raises(ValidationError):
        NewsisNarrowedCandidate(**{**candidate.model_dump(), "selected_by": "other"})

    wake_result = NewsisWakeNarrowingResult(
        query="q", raw_item_count=1, deduped_item_count=1,
        literal_match_count=0, candidates=(candidate,),
    )
    with pytest.raises(ValidationError):
        wake_result.query = "changed"
    with pytest.raises(ValidationError):
        NewsisWakeNarrowingResult(**wake_result.model_dump(), extra_field=True)

    batch = NewsisCandidateNarrowingBatch(
        results=(wake_result,), requested_model="requested", actual_model="actual",
        narrowed_at=datetime(2099, 1, 2, tzinfo=timezone.utc),
    )
    with pytest.raises(ValidationError):
        batch.requested_model = "changed"
    with pytest.raises(ValidationError):
        NewsisCandidateNarrowingBatch(**batch.model_dump(), extra_field=True)


def test_one_embeddings_only_call_and_exact_order_and_allowed_wake_fields():
    contexts = (
        GoogleContextRef(source="첫 출처", title="첫 제목", url="https://sentinel.invalid/one"),
        GoogleContextRef(source="둘째 출처", title="둘째 제목", url="https://sentinel.invalid/two"),
    )
    items = (item(1, "제목1", "설명1"), item(2, "제목2", "설명2"))
    fake = client([[1, 0], [0, 1], [1, 0]])
    batch = narrow_newsis_candidates(wakes=(wake(contexts=contexts),), items=items, client=fake)
    assert len(fake.embeddings.calls) == 1
    assert not hasattr(fake, "responses")
    call = fake.embeddings.calls[0]
    assert call["model"] == DEFAULT_NEWSIS_NARROWING_MODEL
    assert call["input"] == [
        "NEWS ARTICLE\nTITLE: 제목1\nDESCRIPTION: 설명1",
        "NEWS ARTICLE\nTITLE: 제목2\nDESCRIPTION: 설명2",
        "GOOGLE SEARCH WAKE\nQUERY: 임지민\nGOOGLE CONTEXT:\n1. [첫 출처] 첫 제목\n2. [둘째 출처] 둘째 제목",
    ]
    serialized = "\n".join(call["input"])
    for forbidden in ("sentinel.invalid", "SENTINEL_TRAFFIC", "987654", "2099-01-02"):
        assert forbidden not in serialized
    assert batch.actual_model == "actual-embedding-model"
    assert batch.narrowed_at >= fake.embeddings.call_completed_at


def test_zero_context_wake_sends_exact_composite_embedding_input():
    fake = client([[1, 0], [1, 0]])
    narrow_newsis_candidates(
        wakes=(wake("정확한 질의"),), items=(item(1, "기사"),), client=fake,
    )
    assert fake.embeddings.calls[0]["input"][-1] == (
        "GOOGLE SEARCH WAKE\nQUERY: 정확한 질의\nGOOGLE CONTEXT: none"
    )


def test_oversized_html_description_is_bounded_only_for_semantic_embedding():
    title = "지드래곤·태양·대성 빅뱅 20주년 기획된 우상의 틀을 깨고 대중과 팬덤을 만나다"
    literal_phrase = "삼천자뒤에만있는검색문구"
    raw_description = (
        "<p>한국 음악 이야기 &#039;첫 장면&#039;\n\t 반복   공백</p>"
        + "<p>긴 한국어 본문 <br />문화와 예술을 다룬 문장입니다.</p>" * 300
        + f"<img src='sentinel.jpg' /> {literal_phrase}"
    )
    assert len(raw_description) > 11_000
    original_item = item(1, title, raw_description, feed="entertain")
    fake = client([[1, 0], [1, 0]])

    result = narrow_newsis_candidates(
        wakes=(wake(literal_phrase),), items=(original_item,), client=fake,
    ).results[0]

    document_text, wake_text = fake.embeddings.calls[0]["input"]
    prefix = f"NEWS ARTICLE\nTITLE: {title}\nDESCRIPTION: "
    assert document_text.startswith(prefix)
    embedded_description = document_text[len(prefix):]
    assert len(embedded_description) == 3_000
    assert "한국 음악 이야기 '첫 장면' 반복 공백" in embedded_description
    assert all(tag not in document_text for tag in ("<p>", "<br />", "<img"))
    assert "\n" not in embedded_description
    assert "\t" not in embedded_description
    assert "  " not in embedded_description
    assert raw_description not in document_text
    assert literal_phrase not in embedded_description
    assert wake_text == (
        f"GOOGLE SEARCH WAKE\nQUERY: {literal_phrase}\nGOOGLE CONTEXT: none"
    )
    assert original_item.description == raw_description
    assert result.literal_match_count == 1
    assert result.candidates[0].literal_match is True
    assert result.candidates[0].description == raw_description


def test_successful_response_without_model_preserves_requested_model_and_reports_none():
    embeddings = FakeEmbeddings([[1, 0], [1, 0]])

    def create_without_model(**kwargs):
        embeddings.calls.append(kwargs)
        return SimpleNamespace(
            data=[SimpleNamespace(embedding=vector) for vector in embeddings.vectors]
        )

    embeddings.create = create_without_model
    batch = narrow_newsis_candidates(
        wakes=(wake(),), items=(item(1, "기사"),),
        client=SimpleNamespace(embeddings=embeddings), model="requested-model",
    )
    assert batch.requested_model == "requested-model"
    assert batch.actual_model is None


def test_exact_url_dedupe_preserves_first_content_and_ordered_unique_feeds():
    duplicate_url = "https://newsis.test/same"
    items = (
        item(1, "first", "first description", "sports", duplicate_url),
        item(2, "second", "second description", "society", duplicate_url),
        item(3, "third", "third description", "sports", duplicate_url),
    )
    fake = client([[1, 0], [1, 0]])
    result = narrow_newsis_candidates(wakes=(wake("none"),), items=items, client=fake).results[0]
    assert result.raw_item_count == 3 and result.deduped_item_count == 1
    assert len(fake.embeddings.calls[0]["input"]) == 2
    candidate = result.candidates[0]
    assert (candidate.title, candidate.description, candidate.published_at_raw) == (
        "first", "first description", "published-1"
    )
    assert candidate.feeds == ("sports", "society")


def test_nfkc_casefold_alphanumeric_complete_query_literal_match():
    items = (item(1, "Ａb-Ｃ 류 중 일", "suffix"), item(2, "unrelated"))
    result = narrow_newsis_candidates(
        wakes=(wake("abｃ류중일"),), items=items, client=client([[1, 0], [0, 1], [1, 0]])
    ).results[0]
    assert result.literal_match_count == 1
    assert result.candidates[0].url.endswith("/1")
    assert result.candidates[0].literal_match is True


def test_independent_quotas_union_labels_broad_query_and_semantic_ranking():
    # Six literals plus three non-literals: literal ranking favors 4,5,6 while the
    # independent semantic top three favors 7,8,9, producing the full six slots.
    items = tuple(item(i, f"돈 story {i}" if i <= 6 else f"other {i}") for i in range(1, 10))
    doc_vectors = [[score, 1] for score in (1, 2, 3, 7, 8, 9, 12, 11, 10)]
    result = narrow_newsis_candidates(
        wakes=(wake("돈"),), items=items, client=client(doc_vectors + [[1, 0]])
    ).results[0]
    assert result.literal_match_count == 6
    assert [candidate.url.rsplit("/", 1)[1] for candidate in result.candidates] == ["6", "5", "4", "7", "8", "9"]
    assert [candidate.selected_by for candidate in result.candidates] == [
        NewsisCandidateSelection.LITERAL,
        NewsisCandidateSelection.LITERAL,
        NewsisCandidateSelection.LITERAL,
        NewsisCandidateSelection.SEMANTIC,
        NewsisCandidateSelection.SEMANTIC,
        NewsisCandidateSelection.SEMANTIC,
    ]
    assert len(result.candidates) == NEWSIS_MAX_CANDIDATES


def test_overlap_upgrade_golden_two_literals_and_zero_literal_semantic_rescue():
    golden_items = (
        item(1, "임지민 부상 병원 이송"),
        item(2, "KBO 결과", "승 임지민 패 상대"),
        item(3, "다른 기사"),
        item(4, "또 다른 기사"),
    )
    golden = narrow_newsis_candidates(
        wakes=(wake("임지민"),), items=golden_items,
        client=client([[10, 1], [6, 1], [8, 1], [7, 1], [1, 0]]),
    ).results[0]
    assert {candidate.url.rsplit("/", 1)[1] for candidate in golden.candidates} >= {"1", "2"}
    assert next(c for c in golden.candidates if c.url.endswith("/1")).selected_by == NewsisCandidateSelection.LITERAL_AND_SEMANTIC
    assert next(c for c in golden.candidates if c.url.endswith("/2")).selected_by == NewsisCandidateSelection.LITERAL

    rescue_items = tuple(item(i, title) for i, title in enumerate(("이강인 마르세유 경기", "잡음1", "잡음2", "잡음3"), 1))
    rescue = narrow_newsis_candidates(
        wakes=(wake("마르세유 대 아틀레티코"),), items=rescue_items,
        client=client([[10, 1], [3, 1], [2, 1], [1, 1], [1, 0]]),
    ).results[0]
    assert rescue.literal_match_count == 0
    assert rescue.candidates[0].url.endswith("/1")
    assert rescue.candidates[0].selected_by == NewsisCandidateSelection.SEMANTIC


def test_deterministic_url_tie_breaking():
    items = (item(1, "x", url="https://z"), item(2, "x", url="https://a"), item(3, "x", url="https://m"))
    result = narrow_newsis_candidates(
        wakes=(wake("absent"),), items=items, client=client([[1, 0]] * 4)
    ).results[0]
    assert [candidate.url for candidate in result.candidates] == ["https://a", "https://m", "https://z"]


def test_zero_call_paths_are_typed_and_actual_model_is_none():
    fake = client([])
    empty = narrow_newsis_candidates(wakes=(), items=(item(1, "x"),), client=fake, model="override")
    assert isinstance(empty, NewsisCandidateNarrowingBatch)
    assert empty.results == () and empty.actual_model is None and empty.requested_model == "override"
    with_wakes = narrow_newsis_candidates(wakes=(wake(), wake("two")), items=(), client=fake)
    assert len(with_wakes.results) == 2
    assert all(result.candidates == () for result in with_wakes.results)
    assert fake.embeddings.calls == []


def test_embedding_count_mismatch_and_api_error_propagate():
    with pytest.raises(ValueError, match="embedding output count mismatch"):
        narrow_newsis_candidates(wakes=(wake(),), items=(item(1, "x"),), client=client([[1, 0]]))
    failure = RuntimeError("provider failed")
    with pytest.raises(RuntimeError, match="provider failed"):
        narrow_newsis_candidates(
            wakes=(wake(),), items=(item(1, "x"),), client=client([], error=failure)
        )


def test_component_does_not_call_collectors_or_relevance(monkeypatch):
    import ksignal.engine.relevance_classifier as relevance
    import ksignal.engine.source_collectors as collectors

    def forbidden(*args, **kwargs):
        raise AssertionError("forbidden downstream or collector call")

    monkeypatch.setattr(collectors, "collect_newsis_pool", forbidden)
    monkeypatch.setattr(collectors, "collect_google_trends_kr", forbidden)
    monkeypatch.setattr(relevance, "classify_candidate_relevance", forbidden)
    narrow_newsis_candidates(
        wakes=(wake(),), items=(item(1, "x"),), client=client([[1, 0], [1, 0]])
    )
