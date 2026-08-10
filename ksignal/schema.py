from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, Field


class RawItem(BaseModel):
    id: str
    source: str
    source_family: str | None = None
    category: str = "uncategorized"
    title: str = ""
    url: str = ""
    snippet: str = ""
    author: str | None = None
    published_at: str | None = None
    fetched_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    language: str = "ko"
    image_urls: list[str] = Field(default_factory=list)
    local_image_paths: list[str] = Field(default_factory=list)
    screenshot_paths: list[str] = Field(default_factory=list)
    dom_text_path: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class VisionLayout(BaseModel):
    page_type: str = "unknown"
    main_content_summary: str = ""
    main_content_region: str = ""
    comments_region: str = ""
    image_regions: list[str] = Field(default_factory=list)
    ignore_regions: list[str] = Field(default_factory=list)
    visible_images: list[dict[str, Any]] = Field(default_factory=list)
    likely_ads_or_ui: list[str] = Field(default_factory=list)
    what_is_happening: str = ""
    confidence: Literal["low", "medium", "high"] = "medium"
    notes: list[str] = Field(default_factory=list)


class TranslationAudit(BaseModel):
    source_language_confirmed: bool = True
    translation_quality: Literal["pass", "warn", "fail"] = "pass"
    quality_score: int = 80
    issues: list[str] = Field(default_factory=list)
    corrected_literal_translation: str = ""
    corrected_cultural_read: str = ""
    notes: str = ""


class SignalCard(BaseModel):
    source: str
    url: str = ""
    category: str = "uncategorized"
    title_original: str = ""
    title_english: str = ""
    raw_korean_excerpt: str = ""
    literal_translation: str = ""
    cultural_read: str = ""
    business_read: str = ""
    visual_read: str = ""
    tags: list[str] = Field(default_factory=list)
    confidence: Literal["low", "medium", "high"] = "medium"
    translation_audit: TranslationAudit | None = None
    image_paths: list[str] = Field(default_factory=list)
    screenshot_paths: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
