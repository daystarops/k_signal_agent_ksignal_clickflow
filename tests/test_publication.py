from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from ksignal.article_package import (
    ArticlePackage,
    ArticleSection,
    ClaimLimit,
    Receipt,
    SourceRef,
)
from ksignal.engine.evidence import EvidenceDecision
from ksignal.publication import (
    FilesystemPublicationRepository,
    InvalidPublicationTransition,
    PublicationError,
    PublicationIdentity,
    PublicationService,
    PublicationStatus,
    create_publication_record,
    transition_publication,
)


NOW = datetime(2026, 8, 18, 12, tzinfo=timezone.utc)


def article() -> ArticlePackage:
    return ArticlePackage(
        story_id="story-42",
        issue_id="issue-7",
        editorial_slot="card_02",
        article_slug="grounded-headline",
        lane="culture",
        headline="A grounded headline",
        dek="A grounded dek",
        receipt=Receipt(korean="원문", english="Original"),
        sections=[ArticleSection(heading="What happened", purpose="report", body="Body")],
        claim_limit=ClaimLimit(allowed=["fact"], prohibited=[]),
        sources=[SourceRef(label="Source", url="https://example.com")],
    )


def clock(value=NOW):
    return lambda: value


def test_initial_record_from_article_package_does_not_mutate_package():
    package = article()
    before = package.model_dump()
    record = create_publication_record(package, clock=clock())

    assert record.publication_identity == PublicationIdentity(
        issue_id="issue-7", article_slug="grounded-headline"
    )
    assert (record.story_id, record.headline) == ("story-42", "A grounded headline")
    assert record.status is PublicationStatus.READY_FOR_REVIEW
    assert record.created_at == record.updated_at == NOW
    assert package.model_dump() == before
    assert set(ArticlePackage.model_fields) == {
        "story_id", "issue_id", "editorial_slot", "article_slug", "lane", "headline", "dek",
        "internet_read", "receipt", "hero_media", "sections", "claim_limit", "sources",
    }


@pytest.mark.parametrize(
    ("start", "end"),
    [
        (PublicationStatus.READY_FOR_REVIEW, PublicationStatus.APPROVED),
        (PublicationStatus.READY_FOR_REVIEW, PublicationStatus.HELD),
        (PublicationStatus.READY_FOR_REVIEW, PublicationStatus.REJECTED),
        (PublicationStatus.HELD, PublicationStatus.READY_FOR_REVIEW),
        (PublicationStatus.HELD, PublicationStatus.REJECTED),
        (PublicationStatus.APPROVED, PublicationStatus.PUBLISHED),
        (PublicationStatus.APPROVED, PublicationStatus.HELD),
    ],
)
def test_every_permitted_transition(start, end):
    initial = create_publication_record(article(), clock=clock())
    record = initial.model_copy(update={"status": start})
    later = NOW + timedelta(minutes=1)
    updated, event = transition_publication(
        record, end, actor="cli", reason="owner decision", clock=clock(later)
    )

    assert updated.status is end
    assert updated.updated_at == later
    assert updated.created_at == NOW
    assert event.from_status is start and event.to_status is end
    assert event.actor == "cli" and event.reason == "owner decision"
    assert event.publication_identity == record.publication_identity


@pytest.mark.parametrize(
    ("start", "end"),
    [
        (PublicationStatus.READY_FOR_REVIEW, PublicationStatus.PUBLISHED),
        (PublicationStatus.HELD, PublicationStatus.APPROVED),
        (PublicationStatus.REJECTED, PublicationStatus.READY_FOR_REVIEW),
        (PublicationStatus.PUBLISHED, PublicationStatus.APPROVED),
        (PublicationStatus.PUBLISHED, PublicationStatus.HELD),
    ],
)
def test_invalid_transitions_are_explicitly_rejected(start, end):
    record = create_publication_record(article(), clock=clock()).model_copy(
        update={"status": start}
    )
    with pytest.raises(InvalidPublicationTransition, match="cannot transition"):
        transition_publication(record, end, actor="owner", clock=clock())


@pytest.mark.parametrize("actor", ["", "   ", None])
def test_actor_is_required(actor):
    record = create_publication_record(article(), clock=clock())
    with pytest.raises(PublicationError, match="actor must be explicit"):
        transition_publication(
            record, PublicationStatus.APPROVED, actor=actor, clock=clock()  # type: ignore[arg-type]
        )


def test_models_are_strict_and_frozen():
    identity = PublicationIdentity(issue_id="i", article_slug="s")
    with pytest.raises(ValidationError):
        PublicationIdentity(issue_id=1, article_slug="s")  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        PublicationIdentity(issue_id="i", article_slug="s", surprise=True)  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        identity.issue_id = "changed"  # type: ignore[misc]


def test_filesystem_round_trip_and_event_history(tmp_path):
    repository = FilesystemPublicationRepository(tmp_path / "publication")
    times = iter((NOW, NOW + timedelta(minutes=2)))
    service = PublicationService(repository, clock=lambda: next(times))
    initial = service.start_review(article())
    updated, event = service.transition(
        initial.publication_identity, PublicationStatus.APPROVED, actor="owner"
    )

    assert repository.get(initial.publication_identity) == updated
    assert repository.events(initial.publication_identity) == (event,)
    assert len(list((tmp_path / "publication").glob("*.json"))) == 1


def test_filesystem_identity_migration_preserves_history_and_removes_source(tmp_path):
    repository = FilesystemPublicationRepository(tmp_path / "publication")
    service = PublicationService(repository, clock=clock())
    initial = service.start_review(article())
    service.transition(initial.publication_identity, PublicationStatus.APPROVED, actor="owner")
    target = PublicationIdentity(issue_id="issue-7", article_slug="new-readable-slug")

    migrated = repository.migrate_identity(
        initial.publication_identity, target, story_id="story-42"
    )

    assert migrated.publication_identity == target
    assert repository.get(initial.publication_identity) is None
    assert repository.get(target) == migrated
    assert repository.events(target)[0].publication_identity == target
    assert len(list((tmp_path / "publication").glob("*.json"))) == 1


def test_filesystem_identity_migration_refuses_existing_target(tmp_path):
    repository = FilesystemPublicationRepository(tmp_path / "publication")
    source = create_publication_record(article(), clock=clock())
    repository.add(source)
    target_article = article().model_copy(update={"article_slug": "occupied"})
    target = create_publication_record(target_article, clock=clock())
    repository.add(target)
    with pytest.raises(Exception, match="occupied"):
        repository.migrate_identity(
            source.publication_identity, target.publication_identity, story_id="story-42"
        )
    assert repository.get(source.publication_identity) == source


def test_evidence_decision_contract_is_unchanged():
    assert [(item.name, item.value) for item in EvidenceDecision] == [
        ("PASS", "PASS"), ("HOLD", "HOLD"), ("FAIL", "FAIL")
    ]
