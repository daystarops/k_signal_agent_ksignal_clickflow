from __future__ import annotations

import pytest

from ksignal.engine.media_acquisition import MediaCandidate
from ksignal.engine.media_eligibility import MediaEligibilityAssessment, media_candidate_id
from ksignal.engine.media_rights import MediaRightsDisposition, classify_media_rights


def candidate(
    provider="wikimedia_commons", asset_id="asset", *, license_code=None,
    license_version=None, license_url=None, embeddable=None, embed_url=None,
    rights_statement=None, usage_terms=None,
):
    return MediaCandidate(
        provider=provider, provider_asset_id=asset_id,
        media_type="video" if provider == "youtube" else "image",
        title="fixture", creator="creator", source="source",
        media_url="https://media.example/asset",
        landing_url="https://landing.example/asset",
        license_code=license_code, license_version=license_version,
        license_url=license_url, embeddable=embeddable, embed_url=embed_url,
        rights_statement=rights_statement, usage_terms=usage_terms,
    )


def eligible(item, *, temporal="current", value=True):
    return MediaEligibilityAssessment(
        candidate_id=media_candidate_id(item), relevance_status="pass" if value else "fail",
        provenance_status="authoritative", temporal_status=temporal,
        reason="fixture", eligible=value,
    )


def test_standard_youtube_embeddable_is_embed_only():
    item = candidate("youtube", license_code="youtube", embeddable=True,
                     embed_url="https://www.youtube.com/embed/asset")
    result = classify_media_rights(item, eligible(item))
    assert result.disposition == MediaRightsDisposition.EMBED_ONLY
    assert result.attribution_required is False


@pytest.mark.parametrize("embeddable", [False, None])
def test_standard_youtube_not_embeddable_is_link_only_and_never_reusable(embeddable):
    item = candidate("youtube", license_code="youtube", embeddable=embeddable)
    result = classify_media_rights(item, eligible(item))
    assert result.disposition == MediaRightsDisposition.LINK_ONLY
    assert result.disposition != MediaRightsDisposition.REUSE_OK


def test_youtube_creative_commons_is_attribution_aware_reuse():
    item = candidate("youtube", license_code="creativeCommon", embeddable=True,
                     embed_url="https://www.youtube.com/embed/asset")
    result = classify_media_rights(item, eligible(item))
    assert result.disposition == MediaRightsDisposition.REUSE_OK
    assert result.rights_basis == "CC BY"
    assert result.attribution_required is True
    assert "third-party material" in result.reason


def test_wikimedia_cc_by_4_is_reusable_with_attribution():
    item = candidate(license_code="CC BY 4.0", license_version="4.0",
                     license_url="https://creativecommons.org/licenses/by/4.0/")
    result = classify_media_rights(item, eligible(item))
    assert result.disposition == MediaRightsDisposition.REUSE_OK
    assert result.attribution_required is True
    assert result.rights_basis == "CC BY 4.0"


def test_cc_by_sa_preserves_sharealike():
    item = candidate(license_code="CC BY-SA 4.0",
                     license_url="https://creativecommons.org/licenses/by-sa/4.0/")
    result = classify_media_rights(item, eligible(item))
    assert result.disposition == MediaRightsDisposition.REUSE_OK
    assert result.attribution_required is True
    assert "ShareAlike" in result.modification_restrictions


def test_cc_by_nc_requires_review_and_preserves_noncommercial_restriction():
    item = candidate(license_code="CC BY-NC 4.0",
                     license_url="https://creativecommons.org/licenses/by-nc/4.0/")
    result = classify_media_rights(item, eligible(item))
    assert result.disposition == MediaRightsDisposition.MANUAL_REVIEW
    assert result.commercial_restrictions == "NonCommercial use only"
    assert result.attribution_required is True


def test_cc_by_nd_preserves_no_derivatives_restriction():
    item = candidate(license_code="CC BY-ND 4.0",
                     license_url="https://creativecommons.org/licenses/by-nd/4.0/")
    result = classify_media_rights(item, eligible(item))
    assert result.disposition == MediaRightsDisposition.REUSE_OK
    assert "NoDerivatives" in result.modification_restrictions


@pytest.mark.parametrize(
    ("family", "restriction"),
    [("by-nc-sa", "ShareAlike"), ("by-nc-nd", "NoDerivatives")],
)
def test_combined_noncommercial_licenses_preserve_modification_conditions(family, restriction):
    item = candidate(
        license_code=f"CC {family.upper()} 4.0",
        license_url=f"https://creativecommons.org/licenses/{family}/4.0/",
    )
    result = classify_media_rights(item, eligible(item))
    assert result.disposition == MediaRightsDisposition.MANUAL_REVIEW
    assert result.commercial_restrictions == "NonCommercial use only"
    assert restriction in result.modification_restrictions


@pytest.mark.parametrize(
    ("code", "url"),
    [
        ("CC0 1.0", "https://creativecommons.org/publicdomain/zero/1.0/"),
        ("Public domain", "https://creativecommons.org/publicdomain/mark/1.0/"),
    ],
)
def test_cc0_and_public_domain_are_reusable_without_attribution(code, url):
    item = candidate(license_code=code, license_url=url)
    result = classify_media_rights(item, eligible(item))
    assert result.disposition == MediaRightsDisposition.REUSE_OK
    assert result.attribution_required is False


def test_unknown_custom_rights_text_is_preserved_for_manual_review():
    item = candidate(license_code="custom", rights_statement="Copyrighted",
                     usage_terms="Contact creator before use")
    result = classify_media_rights(item, eligible(item))
    assert result.disposition == MediaRightsDisposition.MANUAL_REVIEW
    assert result.rights_basis == "Copyrighted | Contact creator before use"


def test_conflicting_code_version_or_url_requires_manual_review():
    item = candidate(license_code="CC BY 4.0", license_version="3.0",
                     license_url="https://creativecommons.org/licenses/by-sa/4.0/")
    assert classify_media_rights(item, eligible(item)).disposition == MediaRightsDisposition.MANUAL_REVIEW


def test_clean_license_cannot_promote_temporal_mismatch():
    item = candidate(license_code="CC BY 4.0",
                     license_url="https://creativecommons.org/licenses/by/4.0/")
    assessment = MediaEligibilityAssessment(
        candidate_id=media_candidate_id(item), relevance_status="pass",
        provenance_status="authoritative", temporal_status="mismatch",
        reason="wrong period", eligible=False,
    )
    result = classify_media_rights(item, assessment)
    assert result.disposition == MediaRightsDisposition.REJECT


def test_rights_gate_rejects_candidate_id_mismatch():
    item = candidate()
    assessment = eligible(item).model_copy(update={"candidate_id": "wikimedia_commons:other"})
    with pytest.raises(ValueError, match="candidate_id"):
        classify_media_rights(item, assessment)
