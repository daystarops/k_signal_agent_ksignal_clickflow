from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import main
import ksignal.editorial_pipeline as pipeline
from ksignal.article_package import (
    ArticlePackage,
    ArticleSection,
    ClaimLimit,
    Receipt,
    SourceRef,
)
from ksignal.editorial_writer import EditorialWriterOutput, WriterSection
from ksignal.external_editor import ExternalEditorialReview
from ksignal.schema import SignalCard


def job_data():
    return {
        "story_id": "story-04",
        "issue": "002",
        "editorial_slot": "card_04",
        "article_slug": "readable-story",
        "lane": "sports",
        "primary_source_url": "https://primary.example/story",
        "supporting_source_urls": ["https://support.example/report"],
        "allowed_facts": ["The club said “다시 시작” after the match."],
        "forbidden_claims": ["Do not call the response universal."],
    }


def draft(label: str) -> EditorialWriterOutput:
    return EditorialWriterOutput(
        headline=f"{label} headline",
        dek=f"{label} dek",
        internet_read=f"{label} read",
        sections=[WriterSection(heading=f"{label} {i}", body=f"Body {i} — 서울") for i in range(3)],
    )


def review() -> ExternalEditorialReview:
    value = draft("B")
    return ExternalEditorialReview(**value.model_dump(), editor_notes=[])


def provider_item(url: str, title: str, text: str):
    return {
        "url": url,
        "title": title,
        "text": text,
        "title_source_url": url,
        "snippet_source_url": url,
        "title_response_id": f"response-{title}",
        "snippet_response_id": f"response-{title}",
    }


@pytest.fixture
def boundaries(monkeypatch):
    calls = {"captured": []}

    def capture(_self, url):
        calls["captured"].append(url)
        title = "한국어 제목" if "primary" in url else "Supporting title"
        text = "서울에서 열린 경기의 본문입니다." if "primary" in url else "Grounded supporting excerpt."
        return SimpleNamespace(items=[provider_item(url, title, text)])

    monkeypatch.setattr(pipeline.HttpProvider, "capture", capture)
    monkeypatch.setattr(
        pipeline,
        "create_signal_card",
        lambda item: SignalCard(
            source=item.source,
            literal_translation="Literal Korean translation.",
            natural_translation="Natural Korean translation.",
            korean_nuance_read="Nuance.",
            cultural_read="Cultural read.",
            business_read="SECRET BUSINESS INTERPRETATION",
        ),
    )
    monkeypatch.setattr(pipeline, "write_editorial_article", lambda material: draft("A"))
    monkeypatch.setattr(pipeline, "edit_external_draft", lambda value: review())
    monkeypatch.setattr(pipeline, "finalize_editorial_article", lambda value: draft("C"))

    def package(result, material, *, issue_id, article_slug, editorial_slot):
        calls["package_result"] = result
        return ArticlePackage(
            story_id=material.story_id,
            issue_id=issue_id,
            editorial_slot=editorial_slot,
            article_slug=article_slug,
            lane=material.lane,
            headline=result.headline,
            dek=result.dek,
            internet_read=result.internet_read,
            receipt=Receipt(korean=material.original_korean, english=material.literal_translation),
            sections=[ArticleSection(heading=s.heading, purpose="story", body=s.body) for s in result.sections],
            claim_limit=ClaimLimit(allowed=material.allowed_facts, prohibited=[]),
            sources=[SourceRef(label=s.label, url=s.url) for s in material.grounded_sources],
        )

    monkeypatch.setattr(pipeline, "writer_result_to_article_package", package)
    return calls


def test_job_json_validates():
    job = pipeline.EditorialStoryJob.model_validate_json(json.dumps(job_data()))
    assert job.editorial_slot == "card_04"
    assert job.article_slug == "readable-story"
    assert job.forbidden_claims


def test_full_data_flow_and_outputs(tmp_path, monkeypatch, boundaries):
    observed = {}
    language_function = pipeline.create_signal_card

    def language(item):
        observed["language_item"] = item
        return language_function(item)

    def writer(material):
        observed["material"] = material
        return draft("A")

    def external(value):
        observed["external"] = value
        return review()

    def final(value):
        observed["final"] = value
        return draft("C")

    monkeypatch.setattr(pipeline, "create_signal_card", language)
    monkeypatch.setattr(pipeline, "write_editorial_article", writer)
    monkeypatch.setattr(pipeline, "edit_external_draft", external)
    monkeypatch.setattr(pipeline, "finalize_editorial_article", final)

    result = pipeline.run_editorial_story(pipeline.EditorialStoryJob(**job_data()), tmp_path)

    assert boundaries["captured"] == [
        job_data()["primary_source_url"],
        job_data()["supporting_source_urls"][0],
    ]
    assert observed["language_item"].url == job_data()["primary_source_url"]
    assert [s.excerpt for s in observed["material"].grounded_sources] == [
        "서울에서 열린 경기의 본문입니다.",
        "Grounded supporting excerpt.",
    ]
    assert "SECRET BUSINESS INTERPRETATION" not in observed["material"].model_dump_json()
    assert observed["external"].headline == "A headline"
    assert observed["final"].material is observed["material"]
    assert observed["final"].draft_a.headline == "A headline"
    assert observed["final"].draft_b.headline == "B headline"
    assert boundaries["package_result"].headline == "C headline"
    inspection = json.loads(result.inspection_path.read_text(encoding="utf-8"))
    assert [inspection[name]["headline"] for name in ("draft_a", "draft_b", "draft_c")] == [
        "A headline", "B headline", "C headline"
    ]
    assert "서울" in result.inspection_path.read_text(encoding="utf-8")
    assert "“다시 시작”" in result.package_path.read_text(encoding="utf-8")


def test_mismatched_provenance_fails_before_models(tmp_path, monkeypatch):
    item = provider_item("https://primary.example/story", "Title", "Body")
    item["snippet_source_url"] = "https://other.example/story"
    monkeypatch.setattr(
        pipeline.HttpProvider, "capture", lambda _self, _url: SimpleNamespace(items=[item])
    )
    called = []
    monkeypatch.setattr(pipeline, "create_signal_card", lambda _item: called.append(True))

    with pytest.raises(pipeline.EditorialStoryStageError, match="source collection"):
        pipeline.run_editorial_story(pipeline.EditorialStoryJob(**job_data()), tmp_path)
    assert called == []


@pytest.mark.parametrize("failed_stage", ["Draft B", "Draft C"])
def test_final_package_not_written_on_late_draft_failure(
    failed_stage, tmp_path, monkeypatch, boundaries
):
    package_path = tmp_path / "002" / "article_packages" / "card_04.json"
    package_path.parent.mkdir(parents=True)
    package_path.write_text('{"existing": true}', encoding="utf-8")

    def fail(_value):
        raise RuntimeError("model unavailable")

    if failed_stage == "Draft B":
        monkeypatch.setattr(pipeline, "edit_external_draft", fail)
    else:
        monkeypatch.setattr(pipeline, "finalize_editorial_article", fail)
    with pytest.raises(pipeline.EditorialStoryStageError, match=failed_stage):
        pipeline.run_editorial_story(pipeline.EditorialStoryJob(**job_data()), tmp_path)
    assert package_path.read_text(encoding="utf-8") == '{"existing": true}'


def test_cli_accepts_job_and_reports_paths(tmp_path, monkeypatch, capsys):
    job_path = tmp_path / "job.json"
    job_path.write_text(json.dumps(job_data(), ensure_ascii=False), encoding="utf-8")
    result = SimpleNamespace(
        draft_c=draft("C"),
        inspection_path=Path("outputs/issues/002/editorial_runs/card_04.json"),
        package_path=Path("outputs/issues/002/article_packages/card_04.json"),
    )
    monkeypatch.setattr(main, "run_editorial_story", lambda job: result)
    monkeypatch.setattr("sys.argv", ["main.py", "editorial-story", "--job", str(job_path)])

    main.main()

    output = capsys.readouterr().out
    assert "Editorial story complete" in output
    assert "Draft C sections: 3" in output
    assert "editorial_runs" in output and "article_packages" in output
