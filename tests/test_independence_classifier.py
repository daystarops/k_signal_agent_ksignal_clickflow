from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from ksignal.engine.evidence import IndependenceStatus
from ksignal.engine.independence_classifier import (
    DEFAULT_INDEPENDENCE_CLASSIFIER_MODEL,
    DUPLICATE_INDEPENDENCE_CANDIDATE_ID,
    INDEPENDENCE_CANDIDATE_ORDER_MISMATCH,
    INDEPENDENCE_CLASSIFIER_INSTRUCTIONS,
    INDEPENDENCE_COUNT_MISMATCH,
    IndependenceAssignment,
    IndependenceBatch,
    IndependenceCandidate,
    classify_candidate_independence,
)


class FakeResponses:
    def __init__(self, response):
        self.response = response
        self.calls = []
        self.call_completed_at = None

    def create(self, **kwargs):
        self.calls.append(kwargs)
        self.call_completed_at = datetime.now(timezone.utc)
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


class ForbiddenEmbeddings:
    def __init__(self):
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        raise AssertionError("embeddings invoked")


def fake_client(results=(), *, model="actual-mini", response_id="resp_ind_1"):
    response = SimpleNamespace(
        output_text=json.dumps({"results": results}, ensure_ascii=False),
        model=model,
        id=response_id,
    )
    return SimpleNamespace(
        responses=FakeResponses(response), embeddings=ForbiddenEmbeddings()
    )


def candidate(
    candidate_id="youtube:video-a",
    *,
    provider="youtube",
    source_identity="channel-a",
    provider_item_id="video-a",
    url="https://sentinel.invalid/video-a",
    title="Same title",
    source_name="Channel A",
    description="Description",
):
    return IndependenceCandidate(
        candidate_id=candidate_id,
        provider=provider,
        source_name=source_name,
        source_identity=source_identity,
        provider_item_id=provider_item_id,
        url=url,
        title=title,
        description=description,
    )


def output(item, status="uncertain", reason="Metadata does not establish origin."):
    return {"candidate_id": item.candidate_id, "status": status, "reason": reason}


def test_contracts_are_strict_and_frozen():
    item = candidate()
    with pytest.raises(ValidationError):
        IndependenceCandidate(**{**item.model_dump(), "outside": True})
    with pytest.raises(ValidationError):
        item.title = "changed"
    for field in ("candidate_id", "source_name", "source_identity", "url"):
        with pytest.raises(ValidationError):
            IndependenceCandidate(**{**item.model_dump(), field: " "})

    assignment = IndependenceAssignment(
        candidate_id="a",
        duplicate_group_id="duplicate:a",
        independence_group_id="youtube:channel:c",
        independence_status="uncertain",
        counts_toward_independence=False,
        reason="unknown",
    )
    batch = IndependenceBatch(
        results=(assignment,), requested_model="m", actual_model=None,
        response_id=None, classified_at=datetime.now(timezone.utc),
    )
    with pytest.raises(ValidationError):
        assignment.reason = "changed"
    with pytest.raises(ValidationError):
        IndependenceAssignment(**{**assignment.model_dump(), "outside": True})
    with pytest.raises(ValidationError):
        batch.response_id = "changed"
    with pytest.raises(ValidationError):
        IndependenceBatch(**{**batch.model_dump(), "outside": True})


@pytest.mark.parametrize(
    ("status", "counts"),
    [
        (IndependenceStatus.INDEPENDENT, True),
        (IndependenceStatus.DUPLICATE, False),
        (IndependenceStatus.SYNDICATED, False),
        (IndependenceStatus.UNCERTAIN, False),
    ],
)
def test_assignment_accepts_exact_countability_contract(status, counts):
    assignment = IndependenceAssignment(
        candidate_id="a",
        duplicate_group_id="duplicate:a",
        independence_group_id="youtube:channel:c",
        independence_status=status,
        counts_toward_independence=counts,
        reason="contract",
    )
    assert assignment.counts_toward_independence is counts


@pytest.mark.parametrize(
    ("status", "counts"),
    [
        (IndependenceStatus.INDEPENDENT, False),
        (IndependenceStatus.DUPLICATE, True),
        (IndependenceStatus.SYNDICATED, True),
        (IndependenceStatus.UNCERTAIN, True),
    ],
)
def test_assignment_rejects_countability_mismatch(status, counts):
    with pytest.raises(ValidationError, match="counts_toward_independence"):
        IndependenceAssignment(
            candidate_id="a",
            duplicate_group_id="duplicate:a",
            independence_group_id="youtube:channel:c",
            independence_status=status,
            counts_toward_independence=counts,
            reason="contract",
        )


def test_default_model_is_exact():
    assert DEFAULT_INDEPENDENCE_CLASSIFIER_MODEL == "gpt-5-mini"


def test_duplicate_candidate_ids_fail_before_call():
    item = candidate()
    client = fake_client()
    with pytest.raises(ValueError, match=DUPLICATE_INDEPENDENCE_CANDIDATE_ID):
        classify_candidate_independence(candidates=(item, item), client=client)
    assert client.responses.calls == []


@pytest.mark.parametrize("match_by", ["item", "url"])
def test_exact_duplicates_use_first_canonical_and_are_not_sent(match_by):
    first = candidate()
    second = candidate(
        "youtube:video-b", provider_item_id="video-b", url="https://other.invalid",
        source_identity="channel-b",
    )
    if match_by == "item":
        second = second.model_copy(update={"provider_item_id": first.provider_item_id})
    else:
        second = second.model_copy(update={"url": first.url})
    client = fake_client([output(first)])
    batch = classify_candidate_independence(candidates=(first, second), client=client)
    assert [result.duplicate_group_id for result in batch.results] == [
        "duplicate:youtube:video-a", "duplicate:youtube:video-a"
    ]
    assert batch.results[1].independence_group_id == "youtube:channel:channel-a"
    assert batch.results[1].independence_status == IndependenceStatus.DUPLICATE
    assert batch.results[1].counts_toward_independence is False
    sent = json.loads(client.responses.calls[0]["input"])["candidates"]
    assert [item["candidate_id"] for item in sent] == [first.candidate_id]


def test_transitive_duplicates_form_one_component():
    first = candidate("youtube:a", provider_item_id="shared", url="https://a")
    middle = candidate("youtube:b", provider_item_id="shared", url="https://bridge")
    last = candidate("youtube:c", provider_item_id="other", url="https://bridge")
    batch = classify_candidate_independence(
        candidates=(first, middle, last), client=fake_client([output(first)])
    )
    assert {result.duplicate_group_id for result in batch.results} == {"duplicate:youtube:a"}
    assert [result.independence_status for result in batch.results] == [
        IndependenceStatus.UNCERTAIN, IndependenceStatus.DUPLICATE,
        IndependenceStatus.DUPLICATE,
    ]


def test_identical_titles_do_not_duplicate_and_singletons_name_themselves():
    first = candidate()
    second = candidate("youtube:video-b", provider_item_id="video-b", url="https://b")
    batch = classify_candidate_independence(
        candidates=(first, second), client=fake_client([output(first), output(second)])
    )
    assert [result.duplicate_group_id for result in batch.results] == [
        "duplicate:youtube:video-a", "duplicate:youtube:video-b"
    ]


def test_missing_provider_item_ids_do_not_duplicate_distinct_candidates():
    first = candidate(provider_item_id=None, url="https://a")
    second = candidate("youtube:video-b", provider_item_id=None, url="https://b")
    batch = classify_candidate_independence(
        candidates=(first, second), client=fake_client([output(first), output(second)])
    )
    assert [result.duplicate_group_id for result in batch.results] == [
        "duplicate:youtube:video-a", "duplicate:youtube:video-b"
    ]


def test_newsis_is_deterministic_one_publisher_group_and_zero_calls():
    first = candidate("newsis:a", provider="newsis", source_identity="newsis-1",
                      provider_item_id="a", url="https://news/a", source_name="Newsis")
    second = candidate("newsis:b", provider="newsis", source_identity="newsis-2",
                       provider_item_id="b", url="https://news/b", source_name="Newsis")
    client = fake_client()
    batch = classify_candidate_independence(candidates=(first, second), client=client)
    assert client.responses.calls == []
    assert {(r.independence_group_id, r.independence_status,
             r.counts_toward_independence) for r in batch.results} == {
        ("newsis:publisher", IndependenceStatus.INDEPENDENT, True)
    }
    assert batch.actual_model is batch.response_id is None


def test_youtube_groups_follow_channel_but_do_not_imply_independence():
    first = candidate()
    same = candidate("youtube:b", provider_item_id="b", url="https://b")
    other = candidate("youtube:c", provider_item_id="c", url="https://c",
                      source_identity="channel-c")
    batch = classify_candidate_independence(
        candidates=(first, same, other),
        client=fake_client([output(first), output(same), output(other)]),
    )
    assert [r.independence_group_id for r in batch.results] == [
        "youtube:channel:channel-a", "youtube:channel:channel-a",
        "youtube:channel:channel-c",
    ]
    assert all(r.independence_status == IndependenceStatus.UNCERTAIN for r in batch.results)
    assert not any(r.counts_toward_independence for r in batch.results)


def test_one_strict_call_sends_only_allowed_fields_in_order():
    first = candidate(provider_item_id="SENTINEL_ITEM", url="https://SENTINEL_URL")
    second = candidate("youtube:b", provider_item_id="b", url="https://b")
    client = fake_client([output(first), output(second)])
    classify_candidate_independence(candidates=(first, second), client=client)
    assert len(client.responses.calls) == 1
    call = client.responses.calls[0]
    assert call["store"] is False
    assert call["text"]["format"]["type"] == "json_schema"
    assert call["text"]["format"]["strict"] is True
    schema = call["text"]["format"]["schema"]
    assert schema["additionalProperties"] is False
    statuses = schema["properties"]["results"]["items"]["properties"]["status"]["enum"]
    assert set(statuses) == {"independent", "syndicated", "uncertain"}
    assert "duplicate" not in statuses
    sent = json.loads(call["input"])
    assert set(sent) == {"candidates"}
    assert [entry["candidate_id"] for entry in sent["candidates"]] == [
        first.candidate_id, second.candidate_id
    ]
    assert all(set(entry) == {"candidate_id", "channel_id", "channel_title",
                              "title", "description"} for entry in sent["candidates"])
    serialized = call["input"]
    for forbidden in ("SENTINEL_ITEM", "SENTINEL_URL", "timestamp", "relevance",
                      "duplicate_group_id", "independence_group_id"):
        assert forbidden not in serialized


@pytest.mark.parametrize(
    ("results", "error"),
    [([], INDEPENDENCE_COUNT_MISMATCH),
     ([{"candidate_id": "wrong", "status": "uncertain", "reason": "x"}],
      INDEPENDENCE_CANDIDATE_ORDER_MISMATCH)],
)
def test_count_and_order_mismatches_fail_loudly(results, error):
    with pytest.raises(ValueError, match=error):
        classify_candidate_independence(candidates=(candidate(),), client=fake_client(results))


def test_missing_output_and_api_errors_propagate():
    missing = SimpleNamespace(responses=FakeResponses(SimpleNamespace(output_text=None)))
    with pytest.raises(ValueError, match="no output_text"):
        classify_candidate_independence(candidates=(candidate(),), client=missing)
    broken = SimpleNamespace(responses=FakeResponses(RuntimeError("API broke")))
    with pytest.raises(RuntimeError, match="API broke"):
        classify_candidate_independence(candidates=(candidate(),), client=broken)


@pytest.mark.parametrize(
    ("status", "expected", "counts"),
    [("independent", IndependenceStatus.INDEPENDENT, True),
     ("syndicated", IndependenceStatus.SYNDICATED, False),
     ("uncertain", IndependenceStatus.UNCERTAIN, False)],
)
def test_model_status_mapping(status, expected, counts):
    item = candidate()
    result = classify_candidate_independence(
        candidates=(item,), client=fake_client([output(item, status)])
    ).results[0]
    assert result.independence_status == expected
    assert result.counts_toward_independence is counts


def test_response_metadata_and_completion_timestamp():
    item = candidate()
    client = fake_client([output(item)], model="provider-model", response_id="resp-real")
    batch = classify_candidate_independence(candidates=(item,), client=client,
                                            model="requested-model")
    assert batch.requested_model == "requested-model"
    assert batch.actual_model == "provider-model"
    assert batch.response_id == "resp-real"
    assert batch.classified_at.tzinfo == timezone.utc
    assert batch.classified_at >= client.responses.call_completed_at


def test_missing_provider_model_does_not_fall_back_and_empty_makes_no_call():
    item = candidate()
    response = SimpleNamespace(output_text=json.dumps({"results": [output(item)]}), id="r")
    client = SimpleNamespace(responses=FakeResponses(response))
    batch = classify_candidate_independence(candidates=(item,), client=client, model="asked")
    assert batch.actual_model is None and batch.requested_model == "asked"
    empty_client = fake_client()
    empty = classify_candidate_independence(candidates=(), client=empty_client)
    assert empty.results == () and empty_client.responses.calls == []
    assert empty.actual_model is empty.response_id is None
    assert empty.classified_at.tzinfo == timezone.utc


def test_manual_im_ji_min_regression():
    channels = ["숨끼 다이노스", "NC다이노스", "엠엘비 센터 【MLB CENTER】", "숏포츠", "용캐스터"]
    items = tuple(candidate(f"youtube:{i}", source_name=name, source_identity=f"ch-{i}",
                            provider_item_id=str(i), url=f"https://video/{i}",
                            title=("화면출처 티빙 영상 출처 및 저작권 소유 : 티빙"
                                   if i == 4 else "부상 소식"))
                  for i, name in enumerate(channels))
    outputs = [output(item, "syndicated" if i == 4 else "uncertain")
               for i, item in enumerate(items)]
    batch = classify_candidate_independence(candidates=items, client=fake_client(outputs))
    assert [r.independence_status.value for r in batch.results] == [
        "uncertain", "uncertain", "uncertain", "uncertain", "syndicated"
    ]


def test_doctrine_is_protected():
    text = " ".join(INDEPENDENCE_CLASSIFIER_INSTRUCTIONS.lower().split())
    assert "different youtube channel is not evidence of independence" in text
    assert "explicit evidence is required" in text
    assert "review, reaction, recap" in text
    assert "uncertain, under-count it" in text
    assert "do not decide relevance, duplication" in text
    assert "pass/hold/fail" in text


def test_component_never_calls_neighboring_classifiers_or_collectors(monkeypatch):
    import ksignal.engine.relevance_classifier as relevance
    import ksignal.engine.source_collectors as collectors

    def forbidden(*args, **kwargs):
        raise AssertionError("neighbor invoked")

    monkeypatch.setattr(relevance, "classify_candidate_relevance", forbidden)
    monkeypatch.setattr(collectors, "collect_google_trends_kr", forbidden)
    monkeypatch.setattr(collectors, "collect_newsis_pool", forbidden)
    monkeypatch.setattr(collectors, "collect_youtube_search", forbidden)
    item = candidate()
    client = fake_client([output(item)])
    batch = classify_candidate_independence(candidates=(item,), client=client)
    assert len(batch.results) == 1
    assert len(client.responses.calls) == 1
    assert client.embeddings.calls == []
