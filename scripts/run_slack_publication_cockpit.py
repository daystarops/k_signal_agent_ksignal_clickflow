"""Run the local K-Signal Slack publication cockpit over Socket Mode."""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from ksignal.publication import FilesystemPublicationRepository, PublicationService
from ksignal.article_package import ArticlePackage
from ksignal.slack_publication import (
    SlackPublicationInteractionController,
    register_publication_actions,
)


def _required_environment(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Required environment variable is missing: {name}")
    return value


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    load_dotenv(root / ".env")
    bot_token = _required_environment("SLACK_BOT_TOKEN")
    app_token = _required_environment("SLACK_APP_TOKEN")
    _required_environment("SLACK_PUBLICATION_CHANNEL_ID")

    repository = FilesystemPublicationRepository(root / "outputs" / "publication")
    service = PublicationService(repository)
    def article_lookup(identity):
        package_dir = root / "outputs" / "issues" / identity.issue_id / "article_packages"
        for path in package_dir.glob("*.json"):
            article = ArticlePackage.model_validate_json(path.read_text(encoding="utf-8"))
            if article.article_slug == identity.article_slug:
                return article
        raise LookupError(f"ArticlePackage not found for {identity}")
    app = App(token=bot_token)
    register_publication_actions(
        app, SlackPublicationInteractionController(service, article_lookup)
    )
    SocketModeHandler(app, app_token).start()


if __name__ == "__main__":
    main()
