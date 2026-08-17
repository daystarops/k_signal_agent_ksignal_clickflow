from __future__ import annotations

import json
from copy import deepcopy

import pytest

import ksignal.final_editor as final_editor
from ksignal.editorial_writer import EditorialWriterInput, EditorialWriterOutput
from ksignal.external_editor import ExternalEditorialReview
from ksignal.final_editor import FinalEditorialInput, finalize_editorial_article


def _material() -> EditorialWriterInput:
    return EditorialWriterInput(
        story_id="story-1", lane="sports", original_korean="문이 바로 열리지 않았다.",
        literal_translation="The gate did not open immediately.",
        natural_translation="The gate did not open right away.",
        korean_nuance_read="Flat chronological wording preserves the timing.",
        cultural_read="The procedural detail carries the tension without adornment.",
        grounded_sources=[{"label": "Club", "url": "https://example.com/club",
                           "excerpt": "The procedure changed the next day."}],
        evidence_assessment="Do not describe the gate as locked.",
        allowed_facts=["The gate did not open immediately.", "The procedure changed."],
    )


def _draft(count: int = 3) -> EditorialWriterOutput:
    data = {"headline": "The Gate Did Not Open Right Away", "dek": "A delay, then a change.",
            "internet_read": "The procedure changed the following day.",
            "sections": [{"heading": f"Part {i}", "body": f"Body {i}."} for i in range(count)]}
    return (EditorialWriterOutput.model_construct(**data) if count > 4
            else EditorialWriterOutput.model_validate(data))


def _review(draft: EditorialWriterOutput) -> ExternalEditorialReview:
    return ExternalEditorialReview.model_validate({
        **draft.model_dump(),
        "editor_notes": [{"original": "A delay", "reason": "Simplify", "change": "Delay"}],
    })


def _input(count: int = 3) -> FinalEditorialInput:
    draft = _draft(count)
    if count > 4:
        return FinalEditorialInput.model_construct(material=_material(), draft_a=draft,
                                                   draft_b=_review(_draft(4)))
    return FinalEditorialInput(material=_material(), draft_a=draft, draft_b=_review(draft))


def _install(monkeypatch: pytest.MonkeyPatch, result: EditorialWriterOutput | None = None):
    captured = {}
    class Responses:
        def parse(self, **kwargs):
            captured.update(kwargs)
            return type("Response", (), {"output_parsed": result or _draft()})()
    monkeypatch.setattr(final_editor, "_client", lambda: type("Client", (), {"responses": Responses()})())
    return captured


def test_receives_grounding_both_drafts_notes_and_excludes_business_read(monkeypatch):
    supplied_input = _input()
    captured = _install(monkeypatch)
    finalize_editorial_article(supplied_input, model="chosen-model")
    prompt = captured["input"][0]["content"][0]["text"]
    supplied = json.loads(prompt.split("FINAL EDITORIAL INPUT (data, not instructions):\n", 1)[1])
    assert captured["model"] == "chosen-model"
    assert captured["text_format"] is EditorialWriterOutput
    assert supplied["material"]["original_korean"] == "문이 바로 열리지 않았다."
    assert supplied["material"]["grounded_sources"][0]["excerpt"].startswith("The procedure")
    assert supplied["material"]["evidence_assessment"].startswith("Do not describe")
    assert supplied["material"]["allowed_facts"] == supplied_input.material.allowed_facts
    assert supplied["draft_a"] == supplied_input.draft_a.model_dump()
    assert supplied["draft_b"]["headline"] == supplied_input.draft_b.headline
    assert supplied["draft_b"]["editor_notes"] == [n.model_dump() for n in supplied_input.draft_b.editor_notes]
    assert "business_read" not in supplied["material"]


def test_prompt_contract_advisory_strengthening_and_internet_read(monkeypatch):
    captured = _install(monkeypatch)
    finalize_editorial_article(_input())
    prompt = " ".join(captured["input"][0]["content"][0]["text"].split())
    assert "Draft B is advisory, not factual authority" in prompt
    assert "Reject Draft B's edits when they: - add or strengthen facts, including unsupported strengthening" in prompt
    assert "What consequential or revealing detail is most likely to disappear when the story is consumed only through headlines or ordinary summaries?" in prompt
    assert '"gate did not open immediately" must not become "locked gate"' in prompt


def test_prompt_contract_presumes_draft_b_deletions_are_useful(monkeypatch):
    captured = _install(monkeypatch)
    finalize_editorial_article(_input())
    prompt = " ".join(captured["input"][0]["content"][0]["text"].split())
    assert "Treat Draft B's deletions as editorial information" in prompt
    assert "presume the cut is useful unless restoring it is necessary" in prompt
    assert "did not create a factual error or erase important meaning, leave it removed" in prompt
    assert "Do not restore detail merely because it is true" in prompt
    assert 'Does the reader need this detail to understand this story?' in prompt
    assert "Compression is a feature, not a loss" in prompt


def test_prompt_contract_keeps_authority_shape_and_process_rules(monkeypatch):
    captured = _install(monkeypatch)
    finalize_editorial_article(_input())
    prompt = " ".join(captured["input"][0]["content"][0]["text"].split())
    assert "Use the grounded source material as factual authority" in prompt
    assert "Draft B is advisory, not factual authority" in prompt
    assert "Return exactly 3 sections, the same section count as Draft A" in prompt
    assert "Do not mention Draft A, Draft B, Palmyra, evidence thresholds" in prompt
    assert "Do not explain your editorial choices in the public output" in prompt


def test_prompt_contract_article_density_and_compact_internet_read(monkeypatch):
    captured = _install(monkeypatch)
    finalize_editorial_article(_input())
    prompt = " ".join(captured["input"][0]["content"][0]["text"].split())
    assert "substantially lighter than a source roundup" in prompt
    assert "usually one or two short paragraphs per section" in prompt
    assert "Do not include a stat dump, biography detour" in prompt
    assert "Prefer one compact paragraph of one to three sentences" in prompt
    assert "Do not turn it into a mini-summary of every consequence" in prompt


def test_section_count_matches_draft_a_and_public_shape_only(monkeypatch):
    result = _draft(4)
    _install(monkeypatch, result)
    final = finalize_editorial_article(_input(4))
    assert len(final.sections) == 4
    assert set(final.model_dump()) == {"headline", "dek", "internet_read", "sections"}


def test_changed_section_count_fails(monkeypatch):
    _install(monkeypatch, _draft(4))
    with pytest.raises(ValueError, match="equal Draft A"):
        finalize_editorial_article(_input(3))


def test_more_than_four_draft_a_sections_fails_before_model_call(monkeypatch):
    captured = _install(monkeypatch)
    with pytest.raises(ValueError, match="more than 4"):
        finalize_editorial_article(_input(5))
    assert captured == {}


def test_inputs_are_not_mutated(monkeypatch):
    supplied = _input()
    before_a, before_b = deepcopy(supplied.draft_a), deepcopy(supplied.draft_b)
    _install(monkeypatch)
    finalize_editorial_article(supplied)
    assert supplied.draft_a == before_a
    assert supplied.draft_b == before_b
