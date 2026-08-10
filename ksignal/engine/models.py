from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class StrEnum(str, Enum):
    pass


class AccessStatus(StrEnum):
    CAPTURED = "captured"
    DEGRADED = "degraded"
    DENIED = "denied"
    LOST = "lost"
    ERROR = "error"
    PENDING = "pending"


class SourceRole(StrEnum):
    ORIGIN_SIGNAL = "origin_signal"; KOREAN_NATIVE_SIGNAL = "korean_native_signal"
    OFFICIAL_CONTEXT = "official_context"; WESTERN_CONTEXT = "western_context"
    GLOBAL_FANDOM_REACTION = "global_fandom_reaction"; INSTAGRAM_CONTEXT = "instagram_context"
    CREATOR_CONTEXT = "creator_context"; VISUAL_REFERENCE = "visual_reference"
    COMMENT_MOOD = "comment_mood"; HASHTAG_SIGNAL = "hashtag_signal"
    LOCATION_SIGNAL = "location_signal"; PRODUCT_SIGNAL = "product_signal"
    BACKGROUND = "background"; VERIFICATION = "verification"
    COUNTERFRAME = "counterframe"; RECEIPT = "receipt"


class ConfidenceGrade(StrEnum):
    A = "A"; B = "B"; C = "C"; D = "D"


class ProviderStatus(StrEnum):
    UP = "up"; DEGRADED = "degraded"; DOWN = "down"


class SourceType(StrEnum):
    FORUM = "forum"; NEWS = "news"; OFFICIAL = "official"; SOCIAL = "social"
    VIDEO = "video"; IMAGE = "image"; SEARCH_RESULT = "search_result"; BLOG = "blog"
    COMMUNITY = "community"; COMMERCE = "commerce"; UNKNOWN = "unknown"


class SignalVelocityState(StrEnum):
    ACCELERATING = "accelerating"; STABLE = "stable"; DECAYING = "decaying"
    STATIC = "static"; UNKNOWN = "unknown"


class ProviderEvent(BaseModel):
    provider: str
    status: AccessStatus
    failure_mode: str | None = None
    timestamp: datetime = Field(default_factory=utcnow)
    fallback_used: bool = False
    elapsed_ms: int = 0


class CaptureVersion(BaseModel):
    version_id: str = Field(default_factory=lambda: str(uuid4()))
    captured_at: datetime = Field(default_factory=utcnow)
    provider: str
    raw_html_path: str | None = None
    rendered_text_path: str | None = None
    screenshot_path: str | None = None
    mobile_screenshot_path: str | None = None
    thumbnail_path: str | None = None
    extracted_text: str | None = None
    visible_metrics: dict[str, float | int | str | None] = Field(default_factory=dict)
    access_status: AccessStatus = AccessStatus.PENDING
    failure_mode: str | None = None
    error_log: str | None = None
    content_hash: str | None = None
    screenshot_hash: str | None = None
    capture_duration_ms: int = 0
    raw_provider_payload_path: str | None = None


class Claim(BaseModel):
    claim_id: str = Field(default_factory=lambda: str(uuid4()))
    claim_text: str
    supporting_source_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=10)
    confidence_grade: ConfidenceGrade = ConfidenceGrade.D
    classification: str
    scope: str
    notes: str | None = None

    @model_validator(mode="after")
    def taxonomy(self):
        if self.classification not in {"fact", "statement", "discourse", "sentiment", "prediction"}:
            raise ValueError("invalid claim classification")
        if self.scope not in {"specific", "general", "trend"}:
            raise ValueError("invalid claim scope")
        return self


class SourceNode(BaseModel):
    source_id: str = Field(default_factory=lambda: str(uuid4()))
    issue_id: str
    candidate_id: str
    platform: str | None = None
    domain: str | None = None
    url: str
    canonical_url: str | None = None
    title: str | None = None
    language: str | None = None
    country_or_region: str | None = None
    source_roles: list[SourceRole] = Field(default_factory=list)
    source_type: SourceType = SourceType.UNKNOWN
    current_access_status: AccessStatus = AccessStatus.PENDING
    failure_mode: str | None = None
    first_seen_at: datetime = Field(default_factory=utcnow)
    last_captured_at: datetime | None = None
    capture_versions: list[CaptureVersion] = Field(default_factory=list)
    visible_comment_samples: list[str] = Field(default_factory=list)
    hashtags: list[str] = Field(default_factory=list)
    mentions: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    translation_status: str | None = None
    summary: str | None = None
    claims: list[Claim] = Field(default_factory=list)
    creative_value: float = 0
    signal_value: float = 0
    confidence: float = 0
    confidence_grade: ConfidenceGrade = ConfidenceGrade.D
    signal_velocity: SignalVelocityState = SignalVelocityState.UNKNOWN
    primary_provider: str | None = None
    fallback_provider: str | None = None
    capture_history: list[ProviderEvent] = Field(default_factory=list)
    raw_provider_payload_path: str | None = None
    provider_metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def derive_url_fields(self):
        self.canonical_url = self.canonical_url or self.url.split("#")[0]
        self.domain = self.domain or urlparse(self.url).netloc.lower()
        return self


class ProviderHealth(BaseModel):
    provider_id: str
    status: ProviderStatus
    last_success: datetime | None = None
    last_failure: datetime | None = None
    failure_rate_24h: float = 0
    avg_response_time_ms: float = 0
    failure_mode: str | None = None


class SignalVelocity(BaseModel):
    signal_id: str
    window: str
    velocity_score: float
    acceleration: float
    source_count_delta: int = 0
    cross_platform_spread: int = 0
    new_roles_detected: list[str] = Field(default_factory=list)
    metric_delta_summary: dict[str, float] = Field(default_factory=dict)
    interpretation: str = "unknown"
    updated_at: datetime = Field(default_factory=utcnow)

