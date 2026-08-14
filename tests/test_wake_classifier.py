from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from ksignal.engine.source_collectors import GoogleContextRef, GoogleWakeCandidate
from ksignal.engine.wake_classifier import (
    DEFAULT_LANE_CLASSIFIER_MODEL,
    LANE_CLASSIFIER_INSTRUCTIONS,
    LaneConfidence,
    WakeLane,
    classify_wake_lanes,
)


class FakeResponses:
    def __init__(self, response):
        self.response = response
        self.calls = []
        self.call_completed_at = None

    def create(self, **kwargs):
        self.calls.append(kwargs)
        self.call_completed_at = datetime.now(timezone.utc)
        return self.response


def fake_client(results, *, model="gpt-5-mini-2026-08-01", response_id="resp_123"):
    response = SimpleNamespace(
        output_text=json.dumps({"results": results}, ensure_ascii=False),
        model=model,
        id=response_id,
    )
    return SimpleNamespace(responses=FakeResponses(response))


def wake(query, traffic, contexts):
    return GoogleWakeCandidate(
        query=query,
        observed_at=datetime(2026, 8, 14, tzinfo=timezone.utc),
        approx_traffic_raw=traffic,
        approx_traffic_floor=int(traffic.rstrip("+").replace(",", "")),
        context_refs=tuple(
            GoogleContextRef(
                source=source,
                title=title,
                url="https://must-not-be-sent.invalid/context",
            )
            for source, title in contexts
        ),
    )


GOLDEN_WAKES = (
    wake(
        "류중일",
        "1000+",
        (
            ("Daum", "'류중일 감독 아들 집에 홈캠 설치' 前사돈 아들 무죄→유죄"),
            ("뉴스1", "'류중일 아들 집 홈캠 설치' 사돈 가족, 항소심서 유죄로 뒤집혀"),
            ("주간조선", '"신혼집에 홈캠 숨겼다"…류중일 전 사돈 아들, 2심서 무죄 뒤집고 유죄'),
        ),
    ),
    wake(
        "네이버 웹툰",
        "100+",
        (
            ("대한민국 정책브리핑", "'케이-콘텐츠' 불법 유통 대응 국제공조 수사 확대"),
            ("Daum", "네이버웹툰, '1억3000만 방문' 불법웹툰 사이트 3곳 폐쇄"),
            ("전자신문", "문체부-경찰청, 북아프리카 거점 웹툰 불법유통 사이트 폐쇄…운영자 검거"),
        ),
    ),
    wake("t 멤버십", "100+", (("11번가", "멤버십 retail 할인 프로모션"),)),
    wake("돈", "2000+", (("뉴스", "태국 공항에서 한국 원화 환전 거부"),)),
)

GOLDEN_RESULTS = [
    {"query": "류중일", "lane": "society", "confidence": "high", "reason": "항소심 형사 사건"},
    {"query": "네이버 웹툰", "lane": "society", "confidence": "high", "reason": "정부·경찰 단속"},
    {"query": "t 멤버십", "lane": "out_of_scope", "confidence": "high", "reason": "일반 소매 할인"},
    {"query": "돈", "lane": "society", "confidence": "medium", "reason": "원화 환전 거부 이슈"},
]


def test_one_strict_responses_call_contains_only_allowed_wake_fields():
    client = fake_client(GOLDEN_RESULTS)
    batch = classify_wake_lanes(GOLDEN_WAKES, client)

    assert len(client.responses.calls) == 1
    call = client.responses.calls[0]
    assert call["model"] == DEFAULT_LANE_CLASSIFIER_MODEL == "gpt-5-mini"
    assert call["store"] is False
    response_format = call["text"]["format"]
    assert response_format["type"] == "json_schema"
    assert response_format["strict"] is True
    item_schema = response_format["schema"]["properties"]["results"]["items"]
    assert item_schema["additionalProperties"] is False
    assert set(item_schema["properties"]["lane"]["enum"]) == {lane.value for lane in WakeLane}
    assert set(item_schema["properties"]["confidence"]["enum"]) == {
        confidence.value for confidence in LaneConfidence
    }

    sent = json.loads(call["input"])
    assert [item["query"] for item in sent] == [wake.query for wake in GOLDEN_WAKES]
    assert set(sent[0]) == {"query", "approx_traffic_raw", "context"}
    assert set(sent[0]["context"][0]) == {"title", "source"}
    serialized = call["input"]
    assert "https://must-not-be-sent.invalid/context" not in serialized
    assert "approx_traffic_floor" not in serialized
    assert "observed_at" not in serialized
    assert len(batch.classifications) == 4


def test_manual_golden_batch_survives_typed_validation_and_ordering():
    client = fake_client(GOLDEN_RESULTS)
    batch = classify_wake_lanes(GOLDEN_WAKES, client)
    assert [(item.query, item.lane.value, item.confidence.value) for item in batch.classifications] == [
        ("류중일", "society", "high"),
        ("네이버 웹툰", "society", "high"),
        ("t 멤버십", "out_of_scope", "high"),
        ("돈", "society", "medium"),
    ]
    assert batch.requested_model == "gpt-5-mini"
    assert batch.actual_model == "gpt-5-mini-2026-08-01"
    assert batch.response_id == "resp_123"
    assert batch.classified_at.tzinfo == timezone.utc
    assert batch.classified_at >= client.responses.call_completed_at


def test_low_confidence_in_scope_and_high_confidence_out_of_scope_are_valid():
    wakes = GOLDEN_WAKES[:2]
    results = [
        {"query": "류중일", "lane": "sports", "confidence": "low", "reason": "약한 스포츠 맥락"},
        {"query": "네이버 웹툰", "lane": "out_of_scope", "confidence": "high", "reason": "관련 없음"},
    ]
    batch = classify_wake_lanes(wakes, fake_client(results))
    assert batch.classifications[0].lane == WakeLane.SPORTS
    assert batch.classifications[0].confidence == LaneConfidence.LOW
    assert batch.classifications[1].lane == WakeLane.OUT_OF_SCOPE


@pytest.mark.parametrize(
    ("results", "error"),
    [
        (GOLDEN_RESULTS[:-1], "CLASSIFICATION_COUNT_MISMATCH"),
        ([GOLDEN_RESULTS[1], GOLDEN_RESULTS[0], *GOLDEN_RESULTS[2:]], "CLASSIFICATION_QUERY_ORDER_MISMATCH"),
    ],
)
def test_relational_contract_rejects_without_repair(results, error):
    with pytest.raises(ValueError, match=error):
        classify_wake_lanes(GOLDEN_WAKES, fake_client(results))


def test_empty_batch_makes_no_call_and_preserves_override():
    client = fake_client([])
    batch = classify_wake_lanes((), client, model="test-model")
    assert client.responses.calls == []
    assert batch.classifications == ()
    assert batch.requested_model == batch.actual_model == "test-model"
    assert batch.response_id is None
    assert batch.classified_at.tzinfo == timezone.utc


def test_core_policy_doctrine_is_protected():
    normalized = " ".join(LANE_CLASSIFIER_INSTRUCTIONS.lower().split())
    assert "classify why the query is waking now" in normalized
    assert "current-development context outranks permanent entity identity" in normalized
    assert "confidence is audit metadata only" in normalized
    assert "approx_traffic_raw is magnitude only" in normalized
    assert "sensitive radar" in normalized
