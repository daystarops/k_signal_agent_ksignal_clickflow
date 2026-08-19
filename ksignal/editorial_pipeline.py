"""Production orchestration for one owner-approved editorial story."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from .article_package import ArticlePackage
from .editorial_writer import (
    EditorialWriterInput,
    EditorialWriterOutput,
    WriterSource,
    write_editorial_article,
    writer_result_to_article_package,
)
from .engine.providers.http_provider import HttpProvider
from .external_editor import ExternalEditorialReview, edit_external_draft
from .final_editor import FinalEditorialInput, finalize_editorial_article
from .models.openai_client import create_signal_card
from .schema import RawItem, SignalCard


class EditorialStoryJob(BaseModel):
    """The owner-approved sources and factual boundary for one story."""

    model_config = ConfigDict(extra="forbid")

    story_id: str
    issue: str
    editorial_slot: str
    article_slug: str
    lane: str
    primary_source_url: str
    supporting_source_urls: list[str]
    allowed_facts: list[str]
    forbidden_claims: list[str]


class SourceProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str
    title: str
    title_source_url: str
    snippet_source_url: str
    response_id: str


class EditorialStoryRunResult(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    job: EditorialStoryJob
    source_provenance: list[SourceProvenance]
    draft_a: EditorialWriterOutput
    draft_b: ExternalEditorialReview
    draft_c: EditorialWriterOutput
    article_package: ArticlePackage
    inspection_path: Path
    package_path: Path


class EditorialStoryStageError(RuntimeError):
    """A failure annotated with the production stage that stopped the run."""

    def __init__(self, stage: str, error: Exception):
        self.stage = stage
        self.error = error
        super().__init__(f"{stage}: {error}")


def _run_stage(stage: str, operation):
    try:
        return operation()
    except EditorialStoryStageError:
        raise
    except Exception as exc:
        raise EditorialStoryStageError(stage, exc) from exc


def _capture_source(url: str, index: int, lane: str) -> RawItem:
    result = HttpProvider().capture(url)
    if not result.items:
        raise ValueError(f"source capture returned no material for {url}")
    captured: dict[str, Any] = result.items[0]
    item = RawItem(
        id=f"editorial-source-{index}",
        source="Owner-approved URL",
        source_family="editorial_story",
        category=lane,
        title=captured.get("title", ""),
        url=captured.get("url", url),
        snippet=captured.get("text", ""),
        title_source_url=captured.get("title_source_url"),
        snippet_source_url=captured.get("snippet_source_url"),
        title_response_id=captured.get("title_response_id"),
        snippet_response_id=captured.get("snippet_response_id"),
    )
    # Revalidate at the orchestration boundary in case a mocked or mutable item
    # crossed the capture boundary with corrupted provenance.
    item = RawItem.model_validate(item.model_dump())
    if not item.title or not item.snippet:
        raise ValueError(f"source capture returned incomplete text for {url}")
    if not all(
        (
            item.title_source_url,
            item.snippet_source_url,
            item.title_response_id,
            item.snippet_response_id,
        )
    ):
        raise ValueError(f"source capture returned missing provenance for {url}")
    return item


def _provenance(item: RawItem) -> SourceProvenance:
    return SourceProvenance(
        url=item.url,
        title=item.title,
        title_source_url=item.title_source_url or "",
        snippet_source_url=item.snippet_source_url or "",
        response_id=item.title_response_id or "",
    )


def _atomic_json_write(path: Path, value: BaseModel | dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = value.model_dump(mode="json") if isinstance(value, BaseModel) else value
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def run_editorial_story(
    job: EditorialStoryJob,
    output_root: str | Path = "outputs/issues",
) -> EditorialStoryRunResult:
    """Run the frozen editorial chain and persist its two production artifacts."""
    job = EditorialStoryJob.model_validate(job)
    urls = [job.primary_source_url, *job.supporting_source_urls]
    sources = _run_stage(
        "source collection",
        lambda: [_capture_source(url, index, job.lane) for index, url in enumerate(urls)],
    )
    provenance = [_provenance(item) for item in sources]

    language: SignalCard = _run_stage(
        "Language Intelligence", lambda: create_signal_card(sources[0])
    )
    original_korean = "\n\n".join(part for part in (sources[0].title, sources[0].snippet) if part)
    material = _run_stage(
        "editorial writer input",
        lambda: EditorialWriterInput(
            story_id=job.story_id,
            lane=job.lane,
            original_korean=original_korean,
            literal_translation=language.literal_translation,
            natural_translation=language.natural_translation,
            korean_nuance_read=language.korean_nuance_read,
            cultural_read=language.cultural_read,
            grounded_sources=[
                WriterSource(label=item.title, url=approved_url, excerpt=item.snippet)
                for item, approved_url in zip(sources, urls)
            ],
            evidence_assessment="Use only the owner-approved sources and allowed facts supplied here.",
            allowed_facts=job.allowed_facts,
        ),
    )
    draft_a = _run_stage("Draft A", lambda: write_editorial_article(material))
    draft_b = _run_stage("Draft B", lambda: edit_external_draft(draft_a))
    draft_c = _run_stage(
        "Draft C",
        lambda: finalize_editorial_article(
            FinalEditorialInput(material=material, draft_a=draft_a, draft_b=draft_b)
        ),
    )
    article_package = _run_stage(
        "ArticlePackage",
        lambda: writer_result_to_article_package(
            draft_c, material, issue_id=job.issue, article_slug=job.article_slug,
            editorial_slot=job.editorial_slot,
        ),
    )

    root = Path(output_root) / job.issue
    inspection_path = root / "editorial_runs" / f"{job.editorial_slot}.json"
    package_path = root / "article_packages" / f"{job.editorial_slot}.json"
    inspection = {
        "job": job.model_dump(mode="json"),
        "source_provenance": [item.model_dump(mode="json") for item in provenance],
        "language_intelligence": {
            "original_korean": original_korean,
            "literal_translation": language.literal_translation,
            "natural_translation": language.natural_translation,
            "korean_nuance_read": language.korean_nuance_read,
            "cultural_read": language.cultural_read,
        },
        "draft_a": draft_a.model_dump(mode="json"),
        "draft_b": draft_b.model_dump(mode="json"),
        "draft_c": draft_c.model_dump(mode="json"),
    }
    _run_stage("inspection write", lambda: _atomic_json_write(inspection_path, inspection))
    _run_stage("ArticlePackage write", lambda: _atomic_json_write(package_path, article_package))

    return EditorialStoryRunResult(
        job=job,
        source_provenance=provenance,
        draft_a=draft_a,
        draft_b=draft_b,
        draft_c=draft_c,
        article_package=article_package,
        inspection_path=inspection_path,
        package_path=package_path,
    )
