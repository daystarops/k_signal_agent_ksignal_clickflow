# K Signal — Windows click flow

This is built for the exact workflow:

**click → Korean sources are pulled → screenshots/vision context → translation guardrail → newsletter ready → click → n8n pushes it out**

It does **not** scan continuously. It only runs when you click the launcher or batch files.

## What it inspects by default

The configured issue is balanced around four lanes:

1. **Government** — Naver News/Blog queries around Korean policy, Seoul city policy, real estate policy, youth policy.
2. **Idols** — Naver News/Image + TheQoo Square for idol/fandom/entertainment signal.
3. **Sports** — Naver News/Image + FM Korea domestic football for K League/KBO/sports fandom signal.
4. **Local Phenomenon** — Naver News/Blog/Image for Seoul/local trends, Seongsu, popups, MZ consumption, neighborhood texture.

Edit this file to change the range:

```text
configs\sources.yaml
```

## Translation guardrail

Every signal card is audited after translation. The guardrail checks:

- Did the English translation match the Korean source?
- Did the model accidentally treat an ad/sidebar/comment as the main post?
- Did it hallucinate a business read beyond the source?
- Does the cultural read need correction?

Set this in `.env`:

```env
TRANSLATION_GUARDRAIL=true
```

You can turn it off later if token usage is too high.

## Setup once

1. Unzip the folder.
2. Double-click `setup_windows.bat`.
3. When Notepad opens `.env`, paste:

```env
OPENAI_API_KEY=your_key_here
OPENAI_VISION_MODEL=gpt-5.5
OPENAI_TEXT_MODEL=gpt-5.5
OPENAI_AUDIT_MODEL=gpt-5.5
TRANSLATION_GUARDRAIL=true

NAVER_CLIENT_ID=your_naver_client_id
NAVER_CLIENT_SECRET=your_naver_client_secret

WEBHOOK_URL=your_n8n_webhook_url_here
```

Naver keys are optional but recommended. Without them, Naver API sources return no items and the agent relies on public HTML sources like TheQoo/FM Korea.

## Daily/weekly use

Double-click:

```text
launcher_windows.bat
```

Menu options:

1. **Generate K Signal issue** — the main one-click run.
2. **Inspect one Korean URL** — test a specific page.
3. **Push latest issue to n8n** — sends Markdown, HTML, cards, image paths, screenshot paths.
4. **Generate K Signal issue, then push to n8n** — one-click production mode.
5. **Open latest HTML newsletter** — opens the Tailwind-rendered preview.

## Output files

```text
outputs\newsletter.html      # Tailwind HTML preview
outputs\brief.md             # newsletter-ready Markdown
outputs\signal_cards.jsonl   # structured cards
outputs\raw_items.jsonl      # raw source items
outputs\images\              # downloaded images
outputs\screenshots\         # Playwright screenshots
outputs\vision\              # vision layout JSON
```

## Rendering

The newsletter preview is rendered as static HTML with Tailwind CDN and Korean-safe font fallbacks:

```text
outputs\newsletter.html
```

No branding is locked yet. This is just the first visual layer so the output feels like a culture board, not a terminal dump.
