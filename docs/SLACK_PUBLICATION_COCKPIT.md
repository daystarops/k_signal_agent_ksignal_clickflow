# Slack publication cockpit

Slack is an operations client, not the source of truth:

```text
K-Signal canonical state
        ↓
Slack publication cockpit
        ↓
PublicationService transition
```

Buttons carry only the canonical `(issue_id, article_slug)` identity. On every click, the
adapter reloads the current `PublicationRecord`, requests a transition through
`PublicationService`, and redraws the message from the returned canonical record. Slack channel
and message timestamps remain transport coordinates outside the publication domain.

In this slice, Publish means only the canonical `approved -> published` transition. It does not
upload HTML, deploy a website, distribute a newsletter, notify subscribers, or invoke n8n:

```text
published state
        ↓
future n8n/newsletter distribution
```

## Local development

Set `SLACK_BOT_TOKEN`, `SLACK_APP_TOKEN`, and `SLACK_PUBLICATION_CHANNEL_ID` in `.env`, then run:

```powershell
.\.venv\Scripts\python.exe scripts\run_slack_publication_cockpit.py
```

The Slack app needs Socket Mode enabled, an app-level token with `connections:write`, a bot token
with `chat:write`, and interactivity enabled. The bot must be able to post in the configured
channel. Socket Mode is local-development transport. A hosted deployment may later register
public HTTP interaction endpoints while retaining the same renderer, controller, canonical
identity, and publication-domain service.
