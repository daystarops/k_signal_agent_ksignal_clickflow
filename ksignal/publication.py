"""Canonical, client-independent publication workflow state."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Callable, Protocol

from pydantic import BaseModel, ConfigDict, field_validator

from .article_package import ArticlePackage


class PublicationError(ValueError):
    """Base error for publication contract violations."""


class InvalidPublicationTransition(PublicationError):
    """Raised when a requested status change is not in the transition table."""


class PublicationRecordAlreadyExists(PublicationError):
    """Raised when initial state already exists for an identity."""


class PublicationRecordNotFound(PublicationError):
    """Raised when state does not exist for an identity."""


class PublicationStatus(StrEnum):
    READY_FOR_REVIEW = "ready_for_review"
    APPROVED = "approved"
    HELD = "held"
    REJECTED = "rejected"
    PUBLISHED = "published"


class _FrozenStrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class PublicationIdentity(_FrozenStrictModel):
    """Canonical key: article slug scoped to its issue."""

    issue_id: str
    article_slug: str

    @field_validator("issue_id", "article_slug")
    @classmethod
    def require_value(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be empty")
        return value


class PublicationRecord(_FrozenStrictModel):
    publication_identity: PublicationIdentity
    story_id: str
    issue_id: str
    article_slug: str
    headline: str
    status: PublicationStatus
    created_at: datetime
    updated_at: datetime

    @field_validator("story_id", "issue_id", "article_slug", "headline")
    @classmethod
    def require_value(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be empty")
        return value

    @field_validator("created_at", "updated_at")
    @classmethod
    def require_aware_datetime(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamp must include a timezone")
        return value

    def model_post_init(self, __context: object) -> None:
        if (self.issue_id, self.article_slug) != (
            self.publication_identity.issue_id,
            self.publication_identity.article_slug,
        ):
            raise ValueError("record fields do not match publication_identity")
        if self.updated_at < self.created_at:
            raise ValueError("updated_at must not precede created_at")


class PublicationEvent(_FrozenStrictModel):
    publication_identity: PublicationIdentity
    from_status: PublicationStatus
    to_status: PublicationStatus
    occurred_at: datetime
    actor: str
    reason: str | None = None

    @field_validator("actor")
    @classmethod
    def require_actor(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("actor must be explicit")
        return value

    @field_validator("occurred_at")
    @classmethod
    def require_aware_datetime(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamp must include a timezone")
        return value


VALID_TRANSITIONS: dict[PublicationStatus, frozenset[PublicationStatus]] = {
    PublicationStatus.READY_FOR_REVIEW: frozenset(
        {PublicationStatus.APPROVED, PublicationStatus.HELD, PublicationStatus.REJECTED}
    ),
    PublicationStatus.HELD: frozenset(
        {PublicationStatus.READY_FOR_REVIEW, PublicationStatus.REJECTED}
    ),
    PublicationStatus.APPROVED: frozenset(
        {PublicationStatus.PUBLISHED, PublicationStatus.HELD}
    ),
    PublicationStatus.REJECTED: frozenset(),
    PublicationStatus.PUBLISHED: frozenset(),
}


Clock = Callable[[], datetime]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def create_publication_record(
    article: ArticlePackage, *, clock: Clock = _utc_now
) -> PublicationRecord:
    """Create review state; ArticlePackage existence alone does not approve it."""
    now = clock()
    identity = PublicationIdentity(issue_id=article.issue_id, article_slug=article.article_slug)
    return PublicationRecord(
        publication_identity=identity,
        story_id=article.story_id,
        issue_id=article.issue_id,
        article_slug=article.article_slug,
        headline=article.headline,
        status=PublicationStatus.READY_FOR_REVIEW,
        created_at=now,
        updated_at=now,
    )


def transition_publication(
    record: PublicationRecord,
    to_status: PublicationStatus,
    *,
    actor: str,
    reason: str | None = None,
    clock: Clock = _utc_now,
) -> tuple[PublicationRecord, PublicationEvent]:
    """Apply one explicit transition and return new immutable state plus its event."""
    # Validate actor even when the transition itself is invalid.
    if not isinstance(actor, str) or not actor.strip():
        raise PublicationError("actor must be explicit")
    if not isinstance(to_status, PublicationStatus):
        raise PublicationError("to_status must be a PublicationStatus")
    if to_status not in VALID_TRANSITIONS[record.status]:
        raise InvalidPublicationTransition(f"cannot transition {record.status} -> {to_status}")
    occurred_at = clock()
    if occurred_at < record.updated_at:
        raise PublicationError("transition timestamp must not precede updated_at")
    event = PublicationEvent(
        publication_identity=record.publication_identity,
        from_status=record.status,
        to_status=to_status,
        occurred_at=occurred_at,
        actor=actor,
        reason=reason,
    )
    updated = record.model_copy(update={"status": to_status, "updated_at": occurred_at})
    return updated, event


class PublicationRepository(Protocol):
    def get(self, identity: PublicationIdentity) -> PublicationRecord | None: ...

    def events(self, identity: PublicationIdentity) -> tuple[PublicationEvent, ...]: ...

    def add(self, record: PublicationRecord) -> None: ...

    def save_transition(self, record: PublicationRecord, event: PublicationEvent) -> None: ...


class FilesystemPublicationRepository:
    """Atomic local JSON store, replaceable behind PublicationRepository."""

    def __init__(self, root: str | Path):
        self.root = Path(root)

    def _path(self, identity: PublicationIdentity) -> Path:
        raw = f"{identity.issue_id}\0{identity.article_slug}".encode()
        return self.root / f"{hashlib.sha256(raw).hexdigest()}.json"

    def _read(self, identity: PublicationIdentity) -> dict | None:
        path = self._path(identity)
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def _write(self, identity: PublicationIdentity, payload: dict) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        path = self._path(identity)
        temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        try:
            temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            temporary.replace(path)
        finally:
            if temporary.exists():
                temporary.unlink()

    def get(self, identity: PublicationIdentity) -> PublicationRecord | None:
        payload = self._read(identity)
        return (
            None
            if payload is None
            else PublicationRecord.model_validate_json(json.dumps(payload["record"]))
        )

    def events(self, identity: PublicationIdentity) -> tuple[PublicationEvent, ...]:
        payload = self._read(identity)
        if payload is None:
            return ()
        return tuple(
            PublicationEvent.model_validate_json(json.dumps(item)) for item in payload["events"]
        )

    def add(self, record: PublicationRecord) -> None:
        if self._read(record.publication_identity) is not None:
            raise PublicationRecordAlreadyExists(str(record.publication_identity))
        self._write(
            record.publication_identity,
            {"record": record.model_dump(mode="json"), "events": []},
        )

    def save_transition(self, record: PublicationRecord, event: PublicationEvent) -> None:
        payload = self._read(record.publication_identity)
        if payload is None:
            raise PublicationRecordNotFound(str(record.publication_identity))
        current = PublicationRecord.model_validate_json(json.dumps(payload["record"]))
        if current.status != event.from_status or current.updated_at > event.occurred_at:
            raise PublicationError("stored publication state does not match transition event")
        payload["record"] = record.model_dump(mode="json")
        payload["events"].append(event.model_dump(mode="json"))
        self._write(record.publication_identity, payload)

    def migrate_identity(
        self, source: PublicationIdentity, target: PublicationIdentity, *, story_id: str
    ) -> PublicationRecord:
        """Atomically re-key one verified record while preserving its event history."""
        payload = self._read(source)
        if payload is None:
            raise PublicationRecordNotFound(str(source))
        if self._read(target) is not None:
            raise PublicationRecordAlreadyExists(str(target))
        current = PublicationRecord.model_validate_json(json.dumps(payload["record"]))
        if current.story_id != story_id or source.issue_id != target.issue_id:
            raise PublicationError("publication identity migration does not match story and issue")
        record = current.model_copy(
            update={
                "publication_identity": target,
                "issue_id": target.issue_id,
                "article_slug": target.article_slug,
            }
        )
        events = [
            PublicationEvent.model_validate_json(json.dumps(item)).model_copy(
                update={"publication_identity": target}
            )
            for item in payload["events"]
        ]
        self._write(
            target,
            {
                "record": record.model_dump(mode="json"),
                "events": [event.model_dump(mode="json") for event in events],
            },
        )
        source_path = self._path(source)
        try:
            source_path.unlink()
        except OSError:
            self._path(target).unlink(missing_ok=True)
            raise
        return record


class PublicationService:
    def __init__(self, repository: PublicationRepository, *, clock: Clock = _utc_now):
        self.repository = repository
        self.clock = clock

    def start_review(self, article: ArticlePackage) -> PublicationRecord:
        record = create_publication_record(article, clock=self.clock)
        self.repository.add(record)
        return record

    def get(self, identity: PublicationIdentity) -> PublicationRecord:
        """Resolve current canonical state for a client adapter."""
        record = self.repository.get(identity)
        if record is None:
            raise PublicationRecordNotFound(str(identity))
        return record

    def transition(
        self,
        identity: PublicationIdentity,
        to_status: PublicationStatus,
        *,
        actor: str,
        reason: str | None = None,
    ) -> tuple[PublicationRecord, PublicationEvent]:
        current = self.get(identity)
        record, event = transition_publication(
            current, to_status, actor=actor, reason=reason, clock=self.clock
        )
        self.repository.save_transition(record, event)
        return record, event
