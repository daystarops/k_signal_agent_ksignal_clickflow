"""Validated publication input for a rich K-Signal article."""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


NonEmptyStr = Annotated[str, StringConstraints(min_length=1)]


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Receipt(_StrictModel):
    korean: NonEmptyStr
    english: NonEmptyStr


class MediaRef(_StrictModel):
    path: NonEmptyStr
    caption: str
    credit: str
    source_url: str
    rights_status: NonEmptyStr


class ArticleSection(_StrictModel):
    heading: NonEmptyStr
    purpose: NonEmptyStr
    body: NonEmptyStr
    supporting_media: list[MediaRef] = Field(default_factory=list)


class ClaimLimit(_StrictModel):
    allowed: list[NonEmptyStr]
    prohibited: list[NonEmptyStr]


class SourceRef(_StrictModel):
    label: NonEmptyStr
    url: NonEmptyStr


class ArticlePackage(_StrictModel):
    story_id: NonEmptyStr
    issue_id: NonEmptyStr
    article_slug: NonEmptyStr
    lane: NonEmptyStr
    headline: NonEmptyStr
    dek: NonEmptyStr
    internet_read: str = ""
    receipt: Receipt
    hero_media: MediaRef | None = None
    sections: list[ArticleSection] = Field(min_length=1)
    claim_limit: ClaimLimit
    sources: list[SourceRef] = Field(min_length=1)
