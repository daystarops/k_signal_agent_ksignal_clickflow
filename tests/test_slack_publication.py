import json
from datetime import datetime, timezone

import pytest

from ksignal.article_package import (
    ArticlePackage,
    ArticleSection,
    ClaimLimit,
    Receipt,
    SourceRef,
)
from ksignal.publication import (
    FilesystemPublicationRepository,
    PublicationRecord,
    PublicationService,
    PublicationStatus,
)
from ksignal.slack_publication import (
    ACTION_APPROVE,
    ACTION_HOLD,
    ACTION_PUBLISH,
    ACTION_REJECT,
    ACTION_RETURN_TO_REVIEW,
    ACTION_TRANSITIONS,
    PublicationReviewView,
    SlackPublicationInteractionController,
    SlackPublicationTransport,
    build_publication_review_message,
)


NOW = datetime(2026, 8, 18, 12, tzinfo=timezone.utc)


def article() -> ArticlePackage:
    return ArticlePackage(
        story_id="story-1",
        issue_id="issue-9",
        editorial_slot="card_03",
        article_slug="review-this-story",
        lane="culture",
        headline="Review this story",
        dek="Dek",
        receipt=Receipt(korean="원문", english="Original"),
        sections=[ArticleSection(heading="Heading", purpose="report", body="Body")],
        claim_limit=ClaimLimit(allowed=["fact"], prohibited=[]),
        sources=[SourceRef(label="Source", url="https://example.com")],
    )


class FakeSlackClient:
    def __init__(self):
        self.posts = []
        self.updates = []

    def chat_postMessage(self, **kwargs):
        self.posts.append(kwargs)
        return {"channel": kwargs["channel"], "ts": "123.456"}

    def chat_update(self, **kwargs):
        self.updates.append(kwargs)
        return {"ok": True}


class CountingRepository(FilesystemPublicationRepository):
    def __init__(self, root):
        super().__init__(root)
        self.get_calls = 0

    def get(self, identity):
        self.get_calls += 1
        return super().get(identity)


def service_and_record(tmp_path):
    repository = CountingRepository(tmp_path / "publication")
    service = PublicationService(repository, clock=lambda: NOW)
    return service, service.start_review(article()), repository


def action_ids(message):
    actions = next((block for block in message["blocks"] if block["type"] == "actions"), None)
    return [] if actions is None else [item["action_id"] for item in actions["elements"]]


def message(record):
    return build_publication_review_message(PublicationReviewView(article=article(), record=record))


def action_value(message):
    actions = next(block for block in message["blocks"] if block["type"] == "actions")
    return actions["elements"][0]["value"]


def body(message, action_id, user_id="U123"):
    return {
        "actions": [{"action_id": action_id, "value": action_value(message)}],
        "user": {"id": user_id},
        "container": {"channel_id": "C123", "message_ts": "123.456"},
    }


def test_ready_for_review_block_kit_actions(tmp_path):
    _, record, _ = service_and_record(tmp_path)
    message_value = message(record)

    assert action_ids(message_value) == [ACTION_APPROVE, ACTION_HOLD, ACTION_REJECT]
    assert message_value["text"].startswith("K-Signal publication review")
    assert "issue-9" in str(message_value["blocks"])
    assert "review-this-story" in str(message_value["blocks"])
    assert "Dek" in str(message_value["blocks"])
    assert "ready_for_review" in str(message_value["blocks"])


def test_approved_block_kit_actions(tmp_path):
    service, record, _ = service_and_record(tmp_path)
    record, _ = service.transition(record.publication_identity, PublicationStatus.APPROVED, actor="cli")
    assert action_ids(message(record)) == [ACTION_PUBLISH, ACTION_HOLD]


def test_held_block_kit_actions(tmp_path):
    service, record, _ = service_and_record(tmp_path)
    record, _ = service.transition(record.publication_identity, PublicationStatus.HELD, actor="cli")
    assert action_ids(message(record)) == [
        ACTION_RETURN_TO_REVIEW, ACTION_REJECT
    ]


@pytest.mark.parametrize("status", [PublicationStatus.REJECTED, PublicationStatus.PUBLISHED])
def test_terminal_states_have_no_buttons(tmp_path, status):
    service, record, _ = service_and_record(tmp_path)
    if status is PublicationStatus.PUBLISHED:
        record, _ = service.transition(
            record.publication_identity, PublicationStatus.APPROVED, actor="cli"
        )
    record, _ = service.transition(record.publication_identity, status, actor="cli")
    assert action_ids(message(record)) == []


def test_action_ids_map_to_canonical_statuses():
    assert ACTION_TRANSITIONS == {
        ACTION_APPROVE: PublicationStatus.APPROVED,
        ACTION_HOLD: PublicationStatus.HELD,
        ACTION_REJECT: PublicationStatus.REJECTED,
        ACTION_PUBLISH: PublicationStatus.PUBLISHED,
        ACTION_RETURN_TO_REVIEW: PublicationStatus.READY_FOR_REVIEW,
    }


def test_identity_boundary_contains_only_canonical_key(tmp_path):
    _, record, _ = service_and_record(tmp_path)
    value = json.loads(action_value(message(record)))
    assert value == {"article_slug": "review-this-story", "issue_id": "issue-9"}
    assert "headline" not in value and "status" not in value and "story_id" not in value


def test_successful_action_reloads_state_records_actor_and_updates_message(tmp_path):
    service, record, repository = service_and_record(tmp_path)
    client = FakeSlackClient()
    controller = SlackPublicationInteractionController(service, lambda _identity: article())
    before = repository.get_calls

    changed = controller.handle(
        body(message(record), ACTION_APPROVE, "U456"), client
    )

    assert changed is True
    assert repository.get_calls >= before + 2  # controller resolve + service transition reload
    assert repository.get(record.publication_identity).status is PublicationStatus.APPROVED
    assert repository.events(record.publication_identity)[-1].actor == "slack:U456"
    assert len(client.updates) == 1
    assert "approved" in str(client.updates[0]["blocks"])
    assert action_ids(client.updates[0]) == [ACTION_PUBLISH, ACTION_HOLD]


def test_stale_invalid_action_leaves_state_unchanged_and_refreshes_message(tmp_path):
    service, record, repository = service_and_record(tmp_path)
    client = FakeSlackClient()
    controller = SlackPublicationInteractionController(service, lambda _identity: article())

    changed = controller.handle(
        body(message(record), ACTION_PUBLISH), client
    )

    assert changed is False
    assert repository.get(record.publication_identity).status is PublicationStatus.READY_FOR_REVIEW
    assert repository.events(record.publication_identity) == ()
    assert len(client.updates) == 1
    assert "ready_for_review" in str(client.updates[0]["blocks"])


def test_transport_posts_and_keeps_message_reference_outside_record(tmp_path):
    _, record, _ = service_and_record(tmp_path)
    client = FakeSlackClient()
    reference = SlackPublicationTransport(client, "C999").post_review(
        PublicationReviewView(article=article(), record=record)
    )
    assert (reference.channel_id, reference.message_ts) == ("C999", "123.456")
    assert client.posts[0]["channel"] == "C999"
    assert not ({"channel_id", "message_ts", "slack"} & set(PublicationRecord.model_fields))


def test_readable_slug_review_to_publish_smoke(tmp_path):
    package = article().model_copy(
        update={"article_slug": "im-ji-min-stadium-response", "headline": "Im Ji-min response"}
    )
    repository = FilesystemPublicationRepository(tmp_path / "publication")
    service = PublicationService(repository, clock=lambda: NOW)
    record = service.start_review(package)
    client = FakeSlackClient()
    controller = SlackPublicationInteractionController(service, lambda _identity: package)

    review = build_publication_review_message(
        PublicationReviewView(article=package, record=record)
    )
    assert all(value in str(review["blocks"]) for value in (
        package.headline, package.dek, package.article_slug, "ready_for_review"
    ))
    assert controller.handle(body(review, ACTION_APPROVE, "U-SMOKE"), client)
    approved = repository.get(record.publication_identity)
    assert approved is not None
    approved_message = build_publication_review_message(
        PublicationReviewView(article=package, record=approved)
    )
    assert controller.handle(body(approved_message, ACTION_PUBLISH, "U-SMOKE"), client)

    published = repository.get(record.publication_identity)
    assert published is not None and published.status is PublicationStatus.PUBLISHED
    assert [event.actor for event in repository.events(record.publication_identity)] == [
        "slack:U-SMOKE", "slack:U-SMOKE"
    ]
    assert len(list((tmp_path / "publication").glob("*.json"))) == 1


def test_tokens_do_not_appear_in_adapter_exceptions():
    secret = "xoxb-super-secret-token"
    with pytest.raises(ValueError) as exc:
        SlackPublicationTransport(FakeSlackClient(), "")
    assert secret not in str(exc.value)
