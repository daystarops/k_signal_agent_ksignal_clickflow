from __future__ import annotations

import json
from types import SimpleNamespace

import ksignal.models.openai_client as language
from ksignal.schema import RawItem, SignalCard


class FakeResponses:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(output_text=json.dumps(self.outputs.pop(0), ensure_ascii=False))


def source() -> RawItem:
    return RawItem(
        id="ko-1",
        source="테스트 뉴스",
        category="sports",
        title="구단, 대응 절차를 바꾸기로 했다",
        snippet="구단은 사고 뒤 대응 시간을 줄이겠다고 밝혔다.",
        url="https://example.kr/1",
    )


def language_outputs():
    return [
        {
            "literal_translation": "The club said it would reduce response time after the accident.",
            "natural_translation": "The club pledged a faster response after the accident.",
        },
        {
            "korean_nuance_read": "The wording is formal and attributes the promise directly to the club.",
            "cultural_read": "A Korean reader hears a formal institutional promise, not an independent finding.",
        },
        {"business_read": "The operational response became part of the follow-up story."},
    ]


def test_create_signal_card_runs_three_distinct_language_stages(monkeypatch):
    responses = FakeResponses(language_outputs())
    monkeypatch.setattr(language, "_client", lambda: SimpleNamespace(responses=responses))
    monkeypatch.setenv("TRANSLATION_GUARDRAIL", "false")

    card = language.create_signal_card(source(), model="test-model")

    assert len(responses.calls) == 3
    prompts = [call["input"][0]["content"][0]["text"] for call in responses.calls]
    assert "literal_translation, natural_translation" in prompts[0]
    assert "cultural_read" not in prompts[0]
    assert "business_read" not in prompts[0]
    assert "구단, 대응 절차를 바꾸기로 했다" in prompts[1]
    assert "The club said it would reduce response time" in prompts[1]
    assert "The club pledged a faster response" in prompts[1]
    assert "구단은 사고 뒤 대응 시간을 줄이겠다고 밝혔다" in prompts[2]
    assert "The club said it would reduce response time" in prompts[2]
    assert "The club pledged a faster response" in prompts[2]
    assert "formal and attributes the promise" in prompts[2]
    assert card.literal_translation.startswith("The club said")
    assert card.natural_translation.startswith("The club pledged")
    assert card.korean_nuance_read.startswith("The wording")
    assert card.cultural_read.startswith("A Korean reader")
    assert card.business_read.startswith("The operational response")


def test_old_signal_card_json_loads_with_empty_new_fields():
    old = {"source": "legacy", "literal_translation": "Faithful English"}
    card = SignalCard.model_validate_json(json.dumps(old))
    assert card.natural_translation == ""
    assert card.korean_nuance_read == ""


def test_audit_corrects_language_fields_without_changing_business_read(monkeypatch):
    output = {
        "source_language_confirmed": True,
        "translation_quality": "pass",
        "quality_score": 95,
        "issues": [],
        "corrected_literal_translation": "Correct faithful English.",
        "corrected_natural_translation": "Correct natural English.",
        "corrected_korean_nuance_read": "Correct nuance.",
        "corrected_cultural_read": "Correct conversational read.",
        "notes": "",
    }
    responses = FakeResponses(language_outputs() + [output])
    monkeypatch.setattr(language, "_client", lambda: SimpleNamespace(responses=responses))
    monkeypatch.setenv("TRANSLATION_GUARDRAIL", "true")

    card = language.create_signal_card(source(), model="test-model")

    assert len(responses.calls) == 4
    assert card.literal_translation == "Correct faithful English."
    assert card.natural_translation == "Correct natural English."
    assert card.korean_nuance_read == "Correct nuance."
    assert card.cultural_read == "Correct conversational read."
    assert card.business_read == "The operational response became part of the follow-up story."
    audit_prompt = responses.calls[3]["input"][0]["content"][0]["text"]
    assert source().title in audit_prompt and source().snippet in audit_prompt

