"""Deterministic rights gate for eligibility-approved media metadata.

This module does not perform legal analysis, infer permission from accessibility,
or download media.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, field_validator

from ksignal.engine.media_acquisition import MediaCandidate
from ksignal.engine.media_eligibility import MediaEligibilityAssessment, media_candidate_id
from ksignal.engine.models import StrEnum


class _FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class MediaRightsDisposition(StrEnum):
    REUSE_OK = "reuse_ok"
    EMBED_ONLY = "embed_only"
    LINK_ONLY = "link_only"
    MANUAL_REVIEW = "manual_review"
    REJECT = "reject"


class MediaRightsAssessment(_FrozenModel):
    candidate_id: str
    disposition: MediaRightsDisposition
    rights_basis: str
    attribution_required: bool
    modification_restrictions: str | None
    commercial_restrictions: str | None
    license_code: str | None
    license_url: str | None
    reason: str

    @field_validator("candidate_id", "rights_basis", "reason")
    @classmethod
    def required_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("rights assessment fields must not be empty")
        return value


class _NormalizedLicense(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    family: str
    version: str | None
    attribution_required: bool
    share_alike: bool = False
    no_derivatives: bool = False
    noncommercial: bool = False


_CC_FAMILIES = {"BY", "BY-SA", "BY-ND", "BY-NC", "BY-NC-SA", "BY-NC-ND"}


def _code_license(code: str | None) -> tuple[str, str | None] | None:
    if not code or not code.strip():
        return None
    normalized = re.sub(r"[_\s]+", "-", code.strip().upper())
    normalized = normalized.replace("CREATIVE-COMMONS", "CC")
    if normalized in {"CC0", "CC-0", "PUBLIC-DOMAIN", "PUBLICDOMAIN", "PD"}:
        return ("CC0" if normalized.startswith("CC") else "PUBLIC_DOMAIN", None)
    # The YouTube API's explicit Creative Commons value denotes its CC BY license.
    if normalized in {"CREATIVECOMMON", "CREATIVE-COMMON", "CC"}:
        return "BY", None
    match = re.fullmatch(r"CC-?(BY(?:-NC)?(?:-SA|-ND)?)(?:-?(\d+(?:\.\d+)?))?", normalized)
    if match and match.group(1) in _CC_FAMILIES:
        return match.group(1), match.group(2)
    return None


def _url_license(url: str | None) -> tuple[str, str | None] | None:
    if not url or not url.strip():
        return None
    parsed = urlparse(url.strip())
    host = (parsed.hostname or "").lower()
    parts = [part.lower() for part in parsed.path.split("/") if part]
    if host not in {"creativecommons.org", "www.creativecommons.org"}:
        return None
    if len(parts) >= 3 and parts[0] == "licenses":
        family = parts[1].upper()
        if family in _CC_FAMILIES:
            return family, parts[2]
    if len(parts) >= 3 and parts[:2] == ["publicdomain", "zero"]:
        return "CC0", parts[2]
    if len(parts) >= 2 and parts[:2] == ["publicdomain", "mark"]:
        return "PUBLIC_DOMAIN", parts[2] if len(parts) > 2 else None
    return None


def _normalize_open_license(candidate: MediaCandidate) -> _NormalizedLicense | None:
    by_code = _code_license(candidate.license_code)
    by_url = _url_license(candidate.license_url)
    if by_code is None and by_url is None:
        return None
    if candidate.license_url and by_url is None:
        return None
    if by_code and by_url and by_code[0] != by_url[0]:
        return None
    family = (by_code or by_url)[0]  # type: ignore[index]
    versions = {
        version
        for version in (
            by_code[1] if by_code else None,
            by_url[1] if by_url else None,
            candidate.license_version.strip() if candidate.license_version else None,
        )
        if version
    }
    if len(versions) > 1:
        return None
    version = next(iter(versions), None)
    if family in {"CC0", "PUBLIC_DOMAIN"}:
        return _NormalizedLicense(
            family=family, version=version, attribution_required=False
        )
    tokens = family.split("-")
    return _NormalizedLicense(
        family=f"CC {family}",
        version=version,
        attribution_required=True,
        share_alike="SA" in tokens,
        no_derivatives="ND" in tokens,
        noncommercial="NC" in tokens,
    )


def _assessment(
    candidate: MediaCandidate,
    disposition: MediaRightsDisposition,
    basis: str,
    reason: str,
    *,
    attribution: bool = False,
    modification: str | None = None,
    commercial: str | None = None,
) -> MediaRightsAssessment:
    return MediaRightsAssessment(
        candidate_id=media_candidate_id(candidate),
        disposition=disposition,
        rights_basis=basis,
        attribution_required=attribution,
        modification_restrictions=modification,
        commercial_restrictions=commercial,
        license_code=candidate.license_code,
        license_url=candidate.license_url,
        reason=reason,
    )


def classify_media_rights(
    candidate: MediaCandidate, eligibility: MediaEligibilityAssessment
) -> MediaRightsAssessment:
    """Apply explicit metadata rules after validating the eligibility boundary."""
    candidate_id = media_candidate_id(candidate)
    if eligibility.candidate_id != candidate_id:
        raise ValueError("rights candidate_id does not match eligibility assessment")
    if not eligibility.eligible:
        return _assessment(
            candidate, MediaRightsDisposition.REJECT, "media eligibility gate",
            "Candidate did not pass story, provenance, and temporal eligibility.",
        )

    if candidate.provider == "youtube":
        code = (candidate.license_code or "").strip().lower()
        if code == "youtube":
            if candidate.embeddable is True and candidate.embed_url:
                return _assessment(
                    candidate, MediaRightsDisposition.EMBED_ONLY,
                    "standard YouTube license and provider embed permission",
                    "Provider metadata permits embedding, not audiovisual reuse.",
                )
            return _assessment(
                candidate, MediaRightsDisposition.LINK_ONLY, "standard YouTube license",
                "Provider metadata does not permit embedding or audiovisual reuse.",
            )

    normalized = _normalize_open_license(candidate)
    if normalized:
        label = " ".join(part for part in (normalized.family, normalized.version) if part)
        modification = None
        if normalized.no_derivatives:
            modification = "NoDerivatives: distribute only unadapted material"
        elif normalized.share_alike:
            modification = "ShareAlike: adaptations must use the required compatible license"
        commercial = "NonCommercial use only" if normalized.noncommercial else None
        disposition = (
            MediaRightsDisposition.MANUAL_REVIEW
            if normalized.noncommercial
            else MediaRightsDisposition.REUSE_OK
        )
        reason = f"Explicit {label} metadata"
        if normalized.noncommercial:
            reason += " requires review because commercial publication permission is absent."
        elif candidate.provider == "youtube":
            reason += "; attribution is required and third-party material is not independently cleared."
        else:
            reason += " permits reuse subject to the recorded conditions."
        return _assessment(
            candidate, disposition, label, reason,
            attribution=normalized.attribution_required,
            modification=modification, commercial=commercial,
        )

    preserved_terms = " | ".join(
        value.strip() for value in (candidate.rights_statement, candidate.usage_terms) if value and value.strip()
    )
    basis = preserved_terms or "missing or unrecognized license metadata"
    return _assessment(
        candidate, MediaRightsDisposition.MANUAL_REVIEW, basis,
        "No recognized, internally consistent deterministic license establishes permission.",
    )
