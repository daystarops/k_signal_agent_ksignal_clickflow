from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from ksignal.article_package import ArticlePackage
from ksignal.engine.media_acquisition import MediaCandidate
from ksignal.engine.media_eligibility import (
    MEDIA_ELIGIBILITY_INSTRUCTIONS,
    MediaEligibilityAssessment,
    MediaProvenanceStatus,
    MediaRelevanceStatus,
    MediaStoryContext,
    MediaTemporalStatus,
    classify_media_eligibility,
)


STORY = MediaStoryContext(
    headline="NC pitcher Lim Ji-min hospitalized after being struck by a line drive",
    context=(
        "NC Dinos pitcher 임지민 was hit in the face by a hard-hit ball during the August "
        "14 game at Sajik Baseball Stadium and taken by ambulance for examination."
    ),
    temporal_context="The incident occurred on 2026-08-14.",
)


def candidate(asset_id: str, title: str, *, creator: str = "Source", description: str = ""):
    return MediaCandidate(
        provider="youtube",
        provider_asset_id=asset_id,
        media_type="video",
        title=title,
        description=description,
        published_at=datetime(2026, 8, 14, tzinfo=timezone.utc),
        creator=creator,
        source=f"channel-{asset_id}",
        media_url=f"https://www.youtube.com/watch?v={asset_id}",
        landing_url=f"https://www.youtube.com/watch?v={asset_id}",
    )


def result(item, relevance, provenance, temporal="current", *, eligible=None, reason="fixture"):
    if eligible is None:
        eligible = (
            relevance == "pass"
            and provenance in {"authoritative", "attributable_secondary"}
            and temporal != "mismatch"
        )
    return {
        "candidate_id": f"{item.provider}:{item.provider_asset_id}",
        "relevance_status": relevance,
        "provenance_status": provenance,
        "temporal_status": temporal,
        "reason": reason,
        "eligible": eligible,
    }


class FakeResponses:
    def __init__(self, results):
        self.calls = []
        self.response = SimpleNamespace(
            output_text=json.dumps({"results": results}, ensure_ascii=False),
            model="gpt-5-mini-test",
            id="resp_media_test",
        )

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


def classify(items, results):
    responses = FakeResponses(results)
    client = SimpleNamespace(responses=responses)
    return classify_media_eligibility(STORY, tuple(items), client), responses


def test_correct_person_authoritative_broadcaster_report_passes():
    item = candidate("official", "NC 임지민 강습 타구에 얼굴 맞아 병원 이송", creator="Broadcaster News")
    batch, _ = classify([item], [result(item, "pass", "authoritative")])
    assert batch.results[0].relevance_status == MediaRelevanceStatus.PASS
    assert batch.results[0].provenance_status == MediaProvenanceStatus.AUTHORITATIVE
    assert batch.results[0].eligible is True


def test_correct_story_attributable_secondary_passes_to_rights_gate():
    item = candidate(
        "secondary", "임지민 부상 장면과 경기장 대응", creator="Sports explainer",
        description="Footage credited to the original league broadcast.",
    )
    batch, _ = classify([item], [result(item, "pass", "attributable_secondary")])
    assert batch.results[0].provenance_status == MediaProvenanceStatus.ATTRIBUTABLE_SECONDARY
    assert batch.results[0].eligible is True


def test_same_korean_name_different_person_fails_despite_clean_license_metadata():
    item = MediaCandidate(
        provider="wikimedia_commons", provider_asset_id="123", media_type="image",
        title="임지민 portrait", description="Portrait of musical performer Lim Ji-min",
        creator="Photographer", source="Own work", media_url="https://upload.wikimedia.invalid/x.jpg",
        landing_url="https://commons.wikimedia.invalid/wiki/File:x.jpg", license_code="CC BY",
        license_version="4.0", license_url="https://creativecommons.org/licenses/by/4.0/",
    )
    batch, _ = classify([item], [result(item, "fail", "authoritative", "mismatch")])
    assert batch.results[0].relevance_status == MediaRelevanceStatus.FAIL
    assert batch.results[0].eligible is False


def test_completely_unrelated_baseball_video_fails():
    item = candidate("unrelated", "KBO home run highlights: Bears vs Twins")
    batch, _ = classify([item], [result(item, "fail", "authoritative")])
    assert batch.results[0].eligible is False


def test_relevant_older_context_is_explicit_and_not_automatically_rejected():
    item = candidate("older", "Profile: NC pitcher 임지민", creator="League channel")
    batch, _ = classify([item], [result(item, "pass", "authoritative", "contextual")])
    assert batch.results[0].temporal_status == MediaTemporalStatus.CONTEXTUAL
    assert batch.results[0].eligible is True


def test_inconsistent_eligible_and_status_contract_is_rejected():
    with pytest.raises(ValidationError, match="eligible is inconsistent"):
        MediaEligibilityAssessment.model_validate({
            "candidate_id": "youtube:bad", "relevance_status": "fail",
            "provenance_status": "authoritative", "temporal_status": "current",
            "reason": "wrong person", "eligible": True,
        })


def test_temporal_mismatch_cannot_be_eligible_but_unknown_can_be():
    base = {
        "candidate_id": "youtube:temporal", "relevance_status": "pass",
        "provenance_status": "authoritative", "reason": "fixture",
    }
    with pytest.raises(ValidationError, match="eligible is inconsistent"):
        MediaEligibilityAssessment.model_validate(
            {**base, "temporal_status": "mismatch", "eligible": True}
        )
    unknown = MediaEligibilityAssessment.model_validate(
        {**base, "temporal_status": "unknown", "eligible": True}
    )
    assert unknown.eligible is True


def test_classifier_sends_only_relevance_and_provenance_evidence_not_rights():
    item = candidate("one", "임지민 injury report")
    batch, responses = classify([item], [result(item, "pass", "authoritative")])
    call = responses.calls[0]
    sent = json.loads(call["input"])
    assert set(sent) == {"story", "candidates"}
    assert set(sent["story"]) == {"headline", "context", "temporal_context"}
    assert set(sent["candidates"][0]) == {
        "candidate_id", "provider", "media_type", "title", "description",
        "published_at", "creator", "source", "landing_url",
    }
    assert "license" not in call["input"].lower()
    assert call["text"]["format"]["strict"] is True
    assert batch.results[0].eligible is True


def test_finished_article_package_projects_only_finished_story_copy():
    package = ArticlePackage.model_validate({
        "story_id": "story", "issue_id": "issue", "editorial_slot": "card_01",
        "article_slug": "slug", "lane": "sports",
        "headline": "Finished headline", "dek": "Finished dek", "internet_read": "Finished read",
        "receipt": {"korean": "원문", "english": "translation"},
        "sections": [{"heading": "What happened", "purpose": "narrative", "body": "Finished body"}],
        "claim_limit": {"allowed": ["fact"], "prohibited": []},
        "sources": [{"label": "source", "url": "https://example.test"}],
    })
    projected = MediaStoryContext.from_article_package(package, temporal_context="August 2026")
    assert projected.headline == "Finished headline"
    assert projected.context == "Finished dek\n\nFinished read\n\nWhat happened: Finished body"
    assert projected.temporal_context == "August 2026"
    assert "issue" not in projected.model_dump()
    assert projected.model_config["frozen"] is True


def test_prompt_protects_separate_dimensions_and_scope():
    prompt = " ".join(MEDIA_ELIGIBILITY_INSTRUCTIONS.lower().split())
    assert "different person with the same name" in prompt
    assert "older media is not automatically" in prompt
    assert "copyright or license compatibility" in prompt
    assert "do not infer trust from a brand list" in prompt
    assert "eligible is a strict derived contract" in prompt
    assert "temporal mismatch must never be eligible" in prompt
