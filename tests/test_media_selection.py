from datetime import datetime, timezone

import pytest

from ksignal.article_package import ArticlePackage
from ksignal.engine.media_acquisition import MediaCandidate
from ksignal.engine.media_eligibility import (
    MediaEligibilityAssessment, MediaProvenanceStatus, MediaRelevanceStatus,
    MediaTemporalStatus, media_candidate_id,
)
from ksignal.engine.media_rights import MediaRightsAssessment, MediaRightsDisposition
from ksignal.engine.media_selection import MediaEditorialUtility, select_editorial_media


def article():
    return ArticlePackage.model_validate({
        "story_id": "story", "issue_id": "002", "editorial_slot": "card_02",
        "article_slug": "stadium-response", "lane": "sports", "headline": "Headline",
        "dek": "Dek", "receipt": {"korean": "원문", "english": "Translation"},
        "sections": [{"heading": "Section", "purpose": "report", "body": "Body"}],
        "claim_limit": {"allowed": ["fact"], "prohibited": []},
        "sources": [{"label": "Source", "url": "https://example.test"}],
    })


def candidate(asset_id, media_type="image"):
    return MediaCandidate(
        provider="youtube" if media_type == "video" else "wikimedia_commons",
        provider_asset_id=asset_id, media_type=media_type, title=asset_id,
        published_at=datetime(2026, 8, 15, tzinfo=timezone.utc), creator="Source",
        media_url=f"https://example.test/{asset_id}", landing_url=f"https://example.test/{asset_id}",
        embed_url=f"https://www.youtube.com/embed/{asset_id}" if media_type == "video" else None,
        embeddable=True if media_type == "video" else None,
    )


def assessment(item, *, eligible=True, provenance=MediaProvenanceStatus.AUTHORITATIVE):
    return MediaEligibilityAssessment(
        candidate_id=media_candidate_id(item),
        relevance_status=MediaRelevanceStatus.PASS if eligible else MediaRelevanceStatus.FAIL,
        provenance_status=provenance,
        temporal_status=MediaTemporalStatus.CURRENT,
        reason="fixture", eligible=eligible,
    )


def right(item, disposition):
    return MediaRightsAssessment(
        candidate_id=media_candidate_id(item), disposition=disposition,
        rights_basis="fixture", attribution_required=False,
        modification_restrictions=None, commercial_restrictions=None,
        license_code=None, license_url=None, reason="fixture",
    )


def utility(item, relevance, explanation, video_better=False):
    return MediaEditorialUtility(
        candidate_id=media_candidate_id(item), story_relevance=relevance,
        explanatory_value=explanation, video_materially_better=video_better,
        rationale="explicit editorial utility fixture",
    )


def test_strong_event_video_can_beat_contextual_still_but_video_is_not_automatic():
    still, event_video, mediocre_video = candidate("still"), candidate("event", "video"), candidate("generic", "video")
    items = (still, event_video, mediocre_video)
    result = select_editorial_media(
        article(), items, tuple(assessment(x) for x in items),
        (right(still, MediaRightsDisposition.REUSE_OK), right(event_video, MediaRightsDisposition.EMBED_ONLY), right(mediocre_video, MediaRightsDisposition.EMBED_ONLY)),
        (utility(still, 9, 8), utility(event_video, 10, 10, True), utility(mediocre_video, 4, 3)),
    )
    assert result.primary_candidate_id == media_candidate_id(event_video)
    scores = {x.candidate_id: x for x in result.scores}
    assert scores[media_candidate_id(event_video)].video_event_value == 8
    assert scores[media_candidate_id(mediocre_video)].video_event_value == 0
    assert scores[media_candidate_id(still)].total > scores[media_candidate_id(mediocre_video)].total


@pytest.mark.parametrize("disposition", [MediaRightsDisposition.REJECT, MediaRightsDisposition.MANUAL_REVIEW, MediaRightsDisposition.LINK_ONLY])
def test_non_renderable_rights_never_become_selectable(disposition):
    item = candidate("blocked", "video")
    result = select_editorial_media(
        article(), (item,), (assessment(item),), (right(item, disposition),),
        (utility(item, 10, 10, True),),
    )
    assert result.primary_candidate_id is None
    assert result.rejected_candidate_ids == (media_candidate_id(item),)
    assert result.scores[0].total == 0


def test_wrong_event_is_excluded_despite_reuse_rights():
    item = candidate("wrong-person")
    result = select_editorial_media(
        article(), (item,), (assessment(item, eligible=False),),
        (right(item, MediaRightsDisposition.REUSE_OK),), (utility(item, 10, 10),),
    )
    assert result.primary_candidate_id is None
    assert result.scores[0].selectable is False


def test_candidate_order_mismatch_fails_closed():
    one, two = candidate("one"), candidate("two")
    with pytest.raises(ValueError, match="rights candidate order"):
        select_editorial_media(
            article(), (one, two), (assessment(one), assessment(two)),
            (right(two, MediaRightsDisposition.REUSE_OK), right(one, MediaRightsDisposition.REUSE_OK)),
            (utility(one, 1, 1), utility(two, 1, 1)),
        )


def test_weak_but_selectable_candidate_leaves_slot_unresolved():
    item = candidate("generic", "video")
    result = select_editorial_media(
        article(), (item,), (assessment(item),),
        (right(item, MediaRightsDisposition.EMBED_ONLY),),
        (utility(item, 4, 3),),
    )
    assert result.primary_candidate_id is None
    assert result.scores[0].selectable is True
    assert result.scores[0].total < 85
