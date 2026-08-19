"""Slack presentation adapter for canonical publication state."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, field_validator

from .publication import (
    PublicationError,
    PublicationIdentity,
    PublicationRecord,
    PublicationService,
    PublicationStatus,
)
from .article_package import ArticlePackage


ACTION_APPROVE = "ksignal_publication_approve"
ACTION_HOLD = "ksignal_publication_hold"
ACTION_REJECT = "ksignal_publication_reject"
ACTION_PUBLISH = "ksignal_publication_publish"
ACTION_RETURN_TO_REVIEW = "ksignal_publication_return_to_review"

ACTION_TRANSITIONS: dict[str, PublicationStatus] = {
    ACTION_APPROVE: PublicationStatus.APPROVED,
    ACTION_HOLD: PublicationStatus.HELD,
    ACTION_REJECT: PublicationStatus.REJECTED,
    ACTION_PUBLISH: PublicationStatus.PUBLISHED,
    ACTION_RETURN_TO_REVIEW: PublicationStatus.READY_FOR_REVIEW,
}

_STATUS_ACTIONS: dict[PublicationStatus, tuple[tuple[str, str, str | None], ...]] = {
    PublicationStatus.READY_FOR_REVIEW: (
        ("Approve", ACTION_APPROVE, "primary"),
        ("Hold", ACTION_HOLD, None),
        ("Reject", ACTION_REJECT, "danger"),
    ),
    PublicationStatus.APPROVED: (
        ("Publish", ACTION_PUBLISH, "primary"),
        ("Hold", ACTION_HOLD, None),
    ),
    PublicationStatus.HELD: (
        ("Return to Review", ACTION_RETURN_TO_REVIEW, "primary"),
        ("Reject", ACTION_REJECT, "danger"),
    ),
    PublicationStatus.REJECTED: (),
    PublicationStatus.PUBLISHED: (),
}


class _FrozenStrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class SlackPublicationMessageRef(_FrozenStrictModel):
    """Slack transport coordinates, deliberately separate from PublicationRecord."""

    channel_id: str
    message_ts: str

    @field_validator("channel_id", "message_ts")
    @classmethod
    def require_value(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be empty")
        return value


class PublicationReviewView(_FrozenStrictModel):
    """Editorial package content projected with canonical workflow state."""

    article: ArticlePackage
    record: PublicationRecord

    def model_post_init(self, __context: object) -> None:
        if (self.article.issue_id, self.article.article_slug) != (
            self.record.issue_id,
            self.record.article_slug,
        ):
            raise ValueError("article and publication record identities do not match")


def _action_value(identity: PublicationIdentity) -> str:
    return json.dumps(identity.model_dump(), separators=(",", ":"), sort_keys=True)


def build_publication_review_message(view: PublicationReviewView) -> dict[str, Any]:
    """Render canonical state as Block Kit without making a network call."""
    record = view.record
    status_label = record.status.value.replace("_", " ").title()
    text = f"K-Signal publication review: {record.headline} ({status_label})"
    blocks: list[dict[str, Any]] = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "K-Signal publication review"},
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Preview*\n{view.article.dek}"},
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*{record.headline}"},
            "fields": [
                {"type": "mrkdwn", "text": f"*Issue*\n{record.issue_id}"},
                {"type": "mrkdwn", "text": f"*Article slug*\n{record.article_slug}"},
                {"type": "mrkdwn", "text": f"*Status*\n`{record.status.value}`"},
            ],
        },
    ]
    actions = _STATUS_ACTIONS[record.status]
    if actions:
        value = _action_value(record.publication_identity)
        elements: list[dict[str, Any]] = []
        for label, action_id, style in actions:
            button: dict[str, Any] = {
                "type": "button",
                "text": {"type": "plain_text", "text": label},
                "action_id": action_id,
                "value": value,
            }
            if style:
                button["style"] = style
            elements.append(button)
        blocks.append({"type": "actions", "elements": elements})
    return {"text": text, "blocks": blocks}


class SlackWebClient(Protocol):
    def chat_postMessage(self, **kwargs: Any) -> dict[str, Any]: ...

    def chat_update(self, **kwargs: Any) -> dict[str, Any]: ...


class SlackPublicationTransport:
    def __init__(self, client: SlackWebClient, channel_id: str):
        if not channel_id.strip():
            raise ValueError("Slack publication channel ID is required")
        self.client = client
        self.channel_id = channel_id

    def post_review(self, view: PublicationReviewView) -> SlackPublicationMessageRef:
        response = self.client.chat_postMessage(
            channel=self.channel_id, **build_publication_review_message(view)
        )
        return SlackPublicationMessageRef(
            channel_id=str(response.get("channel") or self.channel_id),
            message_ts=str(response["ts"]),
        )

    def update_review(
        self, reference: SlackPublicationMessageRef, view: PublicationReviewView
    ) -> None:
        self.client.chat_update(
            channel=reference.channel_id,
            ts=reference.message_ts,
            **build_publication_review_message(view),
        )


class SlackPublicationInteractionController:
    """Translate Slack actions into PublicationService calls."""

    def __init__(self, service: PublicationService, article_lookup: Callable[[PublicationIdentity], ArticlePackage]):
        self.service = service
        self.article_lookup = article_lookup

    def _view(self, record: PublicationRecord) -> PublicationReviewView:
        return PublicationReviewView(article=self.article_lookup(record.publication_identity), record=record)

    def handle(self, body: dict[str, Any], client: SlackWebClient) -> bool:
        """Handle an already-acknowledged action; return whether state changed."""
        action = body["actions"][0]
        action_id = action["action_id"]
        if action_id not in ACTION_TRANSITIONS:
            return False
        identity = PublicationIdentity.model_validate_json(action["value"])
        actor = f"slack:{body['user']['id']}"
        reference = SlackPublicationMessageRef(
            channel_id=body["container"]["channel_id"],
            message_ts=body["container"]["message_ts"],
        )

        # Resolve before transition; button payload status is intentionally absent/untrusted.
        current = self.service.get(identity)
        try:
            updated, _event = self.service.transition(
                identity, ACTION_TRANSITIONS[action_id], actor=actor
            )
        except PublicationError:
            # A stale click cannot mutate state. Refresh controls from canonical state.
            current = self.service.get(identity)
            SlackPublicationTransport(client, reference.channel_id).update_review(
                reference, self._view(current)
            )
            return False

        SlackPublicationTransport(client, reference.channel_id).update_review(reference, self._view(updated))
        return True


def register_publication_actions(app: Any, controller: SlackPublicationInteractionController) -> None:
    """Register Bolt listeners; acknowledgement always precedes domain work."""

    def listener(ack: Callable[[], None], body: dict[str, Any], client: SlackWebClient) -> None:
        ack()
        controller.handle(body, client)

    for action_id in ACTION_TRANSITIONS:
        app.action(action_id)(listener)
