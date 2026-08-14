from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from ksignal.engine.relevance_classifier import (
    DEFAULT_RELEVANCE_CLASSIFIER_MODEL,
    DUPLICATE_RELEVANCE_CANDIDATE_ID,
    RELEVANCE_CANDIDATE_ORDER_MISMATCH,
    RELEVANCE_CLASSIFIER_INSTRUCTIONS,
    RELEVANCE_COUNT_MISMATCH,
    CandidateRelevance,
    RelevanceCandidate,
    RelevanceConfidence,
    classify_candidate_relevance,
    relevance_contract_errors,
)
from ksignal.engine.source_collectors import GoogleContextRef, GoogleWakeCandidate


class FakeResponses:
    def __init__(self, response):
        self.response = response
        self.calls = []
        self.call_completed_at = None

    def create(self, **kwargs):
        self.calls.append(kwargs)
        self.call_completed_at = datetime.now(timezone.utc)
        return self.response


def fake_client(results, *, model="gpt-5-mini-2026-08-01", response_id="resp_rel_123"):
    response = SimpleNamespace(
        output_text=json.dumps({"results": results}, ensure_ascii=False),
        model=model,
        id=response_id,
    )
    return SimpleNamespace(responses=FakeResponses(response))


def wake(query="임지민", *, with_context=True):
    contexts = ()
    if with_context:
        contexts = (
            GoogleContextRef(
                source="연합뉴스",
                title='얼굴 강타당한 NC 임지민…"안면부 타박상으로 정밀 검진 예정"(종합)',
                url="https://must-not-be-sent.invalid/google-context",
            ),
            GoogleContextRef(
                source="MBC 뉴스",
                title="NC 투수 임지민, 강습 타구에 맞아 부상‥펜스 문 열리지 않아 구급차 도착 늦어",
                url="https://must-not-be-sent.invalid/google-context-2",
            ),
            GoogleContextRef(
                source="뉴시스",
                title="강습 타구에 얼굴 강타당한 NC 임지민, 구급차로 병원 이송",
                url="https://must-not-be-sent.invalid/google-context-3",
            ),
        )
    return GoogleWakeCandidate(
        query=query,
        observed_at=datetime(2026, 8, 14, tzinfo=timezone.utc),
        approx_traffic_raw="1000+",
        approx_traffic_floor=1000,
        context_refs=contexts,
    )


GAME_RESULT = RelevanceCandidate(
    candidate_id="newsis:NISX20260814_0003750254",
    provider="newsis",
    source="뉴시스",
    title="[KBO 오늘의 경기 결과]8월14일(금)",
    description="NC 9 - 8 롯데(사직) 승 임지민 패 김원중",
    published_at_raw="Fri, 14 Aug 2026 23:30:53 +0900",
)

INJURY_ARTICLE = RelevanceCandidate(
    candidate_id="newsis:NISX20260814_0003750360",
    provider="newsis",
    source="뉴시스",
    title="강습 타구에 얼굴 강타당한 NC 임지민, 구급차로 병원 이송",
    description="강습 타구에 얼굴을 맞아 출혈과 응급 처치를 거쳐 병원으로 이송돼 정밀 검진 예정이다.",
    published_at_raw="Fri, 14 Aug 2026 23:18:35 +0900",
)

YOUTUBE_CANDIDATES = (
    RelevanceCandidate(candidate_id="youtube:0lFRsI7OvVk", provider="youtube", source="숨끼 다이노스", title="임지민 선수의 쾌유를 기원합니다. | 08월 14일 NC 9 : 8 롯데 리뷰", description="", published_at_raw="2026-08-14T15:00:00Z"),
    RelevanceCandidate(candidate_id="youtube:j9EEd9SQMxY", provider="youtube", source="NC다이노스", title="임지민 선수 큰 부상이 아니길 기도합니다 #엔씨다이노스#임지민 #부상 #승리 #구독", description="", published_at_raw="2026-08-14T15:01:00Z"),
    RelevanceCandidate(candidate_id="youtube:iosYCnw5HaY", provider="youtube", source="엠엘비 센터 【MLB CENTER】", title="임지민 안면을 강타한 타구.. 큰 부상이 아니길 바랍니다", description="", published_at_raw="2026-08-14T15:02:00Z"),
    RelevanceCandidate(candidate_id="youtube:xq8eOiiucBI", provider="youtube", source="숏포츠", title="임지민선수의쾌유를바랍니다", description="", published_at_raw="2026-08-14T15:03:00Z"),
    RelevanceCandidate(candidate_id="youtube:dlvgSpzutK4", provider="youtube", source="용캐스터", title="260814_NC 임지민 안면 강타... 허술했던 사직야구장 안전 대응 이슈 : 화면출처 티빙_수익 미창출 영상 (영상 출처 및 저작권 소유 : 티빙)", description="", published_at_raw="2026-08-14T15:04:00Z"),
)

ALL_CANDIDATES = (GAME_RESULT, INJURY_ARTICLE, *YOUTUBE_CANDIDATES)


def result(candidate, relevant, confidence="high", reason="수동 검증 결과"):
    return {
        "candidate_id": candidate.candidate_id,
        "relevant": relevant,
        "confidence": confidence,
        "matched_subject": "임지민",
        "reason": reason,
    }


def test_one_strict_responses_call_sends_only_allowed_fields_in_order():
    outputs = [result(GAME_RESULT, False), result(INJURY_ARTICLE, True)]
    client = fake_client(outputs)
    batch = classify_candidate_relevance(wake(), (GAME_RESULT, INJURY_ARTICLE), client)

    assert len(client.responses.calls) == 1
    call = client.responses.calls[0]
    assert call["model"] == DEFAULT_RELEVANCE_CLASSIFIER_MODEL == "gpt-5-mini"
    assert call["store"] is False
    response_format = call["text"]["format"]
    assert response_format["type"] == "json_schema"
    assert response_format["strict"] is True
    item_schema = response_format["schema"]["properties"]["results"]["items"]
    assert item_schema["additionalProperties"] is False
    assert set(item_schema["properties"]["confidence"]["enum"]) == {
        confidence.value for confidence in RelevanceConfidence
    } == {"high", "medium", "low"}

    sent = json.loads(call["input"])
    assert set(sent) == {"wake", "candidates"}
    assert set(sent["wake"]) == {"query", "context"}
    assert all(set(context) == {"title", "source"} for context in sent["wake"]["context"])
    assert [item["candidate_id"] for item in sent["candidates"]] == [
        GAME_RESULT.candidate_id,
        INJURY_ARTICLE.candidate_id,
    ]
    allowed = {"candidate_id", "provider", "source", "title", "description", "published_at_raw"}
    assert all(set(item) == allowed for item in sent["candidates"])
    serialized = call["input"]
    assert "https://must-not-be-sent.invalid/google-context" not in serialized
    assert "approx_traffic_raw" not in serialized
    assert "approx_traffic_floor" not in serialized
    assert "observed_at" not in serialized
    assert len(batch.results) == 2


def test_candidate_contract_forbids_url_and_requires_nonempty_id():
    assert "url" not in RelevanceCandidate.model_fields
    with pytest.raises(ValidationError):
        RelevanceCandidate(**{**GAME_RESULT.model_dump(), "url": "https://invalid.example"})
    with pytest.raises(ValidationError):
        RelevanceCandidate(**{**GAME_RESULT.model_dump(), "candidate_id": " "})


def test_duplicate_candidate_ids_fail_before_model_call():
    client = fake_client([])
    with pytest.raises(ValueError, match=DUPLICATE_RELEVANCE_CANDIDATE_ID):
        classify_candidate_relevance(wake(), (GAME_RESULT, GAME_RESULT), client)
    assert client.responses.calls == []


def test_manual_normal_context_golden_fixture_preserves_real_ids_and_results():
    outputs = [result(GAME_RESULT, False), *[result(item, True) for item in ALL_CANDIDATES[1:]]]
    batch = classify_candidate_relevance(wake(), ALL_CANDIDATES, fake_client(outputs))
    assert [item.candidate_id for item in batch.results] == [item.candidate_id for item in ALL_CANDIDATES]
    assert [(item.relevant, item.confidence.value, item.matched_subject) for item in batch.results] == [
        (False, "high", "임지민"),
        *[(True, "high", "임지민")] * 6,
    ]
    assert YOUTUBE_CANDIDATES[3].title == "임지민선수의쾌유를바랍니다"


def test_entity_only_no_context_manual_fixture_is_false_low():
    candidates = (GAME_RESULT, INJURY_ARTICLE)
    outputs = [result(item, False, "low", "wake event context missing") for item in candidates]
    batch = classify_candidate_relevance(wake("임지민", with_context=False), candidates, fake_client(outputs))
    assert [(item.relevant, item.confidence.value) for item in batch.results] == [(False, "low"), (False, "low")]


def test_event_enriched_no_context_manual_fixture_is_judged_normally():
    candidates = (GAME_RESULT, INJURY_ARTICLE)
    outputs = [result(GAME_RESULT, False), result(INJURY_ARTICLE, True)]
    batch = classify_candidate_relevance(wake("임지민 부상", with_context=False), candidates, fake_client(outputs))
    assert [(item.relevant, item.confidence.value) for item in batch.results] == [(False, "high"), (True, "high")]


@pytest.mark.parametrize(
    ("outputs", "error"),
    [
        ([result(GAME_RESULT, False)], RELEVANCE_COUNT_MISMATCH),
        ([result(INJURY_ARTICLE, True), result(GAME_RESULT, False)], RELEVANCE_CANDIDATE_ORDER_MISMATCH),
    ],
)
def test_relational_contract_rejects_count_or_order_without_repair(outputs, error):
    with pytest.raises(ValueError, match=error):
        classify_candidate_relevance(wake(), (GAME_RESULT, INJURY_ARTICLE), fake_client(outputs))


def test_contract_helper_reports_stable_errors():
    one = CandidateRelevance.model_validate(result(GAME_RESULT, False))
    assert relevance_contract_errors((GAME_RESULT, INJURY_ARTICLE), (one,)) == (
        RELEVANCE_COUNT_MISMATCH,
        RELEVANCE_CANDIDATE_ORDER_MISMATCH,
    )


@pytest.mark.parametrize("relevant", [True, False])
def test_low_confidence_boolean_is_valid_and_preserved(relevant):
    batch = classify_candidate_relevance(
        wake(), (GAME_RESULT,), fake_client([result(GAME_RESULT, relevant, "low")])
    )
    assert batch.results[0].relevant is relevant
    assert batch.results[0].confidence == RelevanceConfidence.LOW
    assert batch.results[0].matched_subject == "임지민"


def test_response_metadata_and_success_completion_timestamp_are_preserved():
    client = fake_client([result(GAME_RESULT, False)], model="actual-model", response_id="resp_xyz")
    batch = classify_candidate_relevance(wake(), (GAME_RESULT,), client, model="requested-model")
    assert batch.requested_model == "requested-model"
    assert batch.actual_model == "actual-model"
    assert batch.response_id == "resp_xyz"
    assert batch.classified_at.tzinfo == timezone.utc
    assert batch.classified_at >= client.responses.call_completed_at


def test_empty_batch_makes_no_call_and_preserves_override():
    client = fake_client([])
    batch = classify_candidate_relevance(wake(), (), client, model="test-model")
    assert client.responses.calls == []
    assert batch.results == ()
    assert batch.requested_model == batch.actual_model == "test-model"
    assert batch.response_id is None
    assert batch.classified_at.tzinfo == timezone.utc


def test_absent_output_text_fails_explicitly():
    client = SimpleNamespace(responses=FakeResponses(SimpleNamespace(output_text=None)))
    with pytest.raises(ValueError, match="no output_text"):
        classify_candidate_relevance(wake(), (GAME_RESULT,), client)


def test_core_relevance_doctrine_is_protected():
    normalized = " ".join(RELEVANCE_CLASSIFIER_INSTRUCTIONS.lower().split())
    assert "same subject is not sufficient" in normalized
    assert "same setting is not sufficient" in normalized
    assert "entity-only or subject-only" in normalized
    assert "do not invent a missing development" in normalized
    assert "event-enriched query can itself supply" in normalized
    assert "matched_subject is not proof of relevance" in normalized
    assert "independence" in normalized and "do not make" in normalized
    assert "confidence is relevance-certainty audit metadata only" in normalized
