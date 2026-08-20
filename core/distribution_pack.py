from __future__ import annotations

import csv
import os
import shutil
import stat
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

DEFAULT_PUBLIC_ISSUE_URL = "https://k-signal.com/"
FEED_NAMES = (
    "01-global-kpop-fandom.png",
    "02-billlie-work-zap.png",
    "03-kleague-starter-pack.png",
    "04-lingard-fc-seoul.png",
)
BG = "#e6e1d6"
INK = "#101828"
RED = "#ef3f36"
PAPER = "#f5f0e4"


def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    candidates = {
        "bold": ("C:/Windows/Fonts/arialbd.ttf", "C:/Windows/Fonts/Arial.ttf"),
        "serif": ("C:/Windows/Fonts/georgiab.ttf", "C:/Windows/Fonts/georgia.ttf"),
        "regular": ("C:/Windows/Fonts/arial.ttf",),
    }
    for candidate in candidates[name]:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size)
    return ImageFont.load_default()


def _remove_tree(path: Path) -> None:
    def unlock_and_retry(function, target, _error):
        Path(target).chmod(stat.S_IWRITE)
        function(target)
    shutil.rmtree(path, onerror=unlock_and_retry)


def _fit_logo(logo_path: Path, width: int) -> Image.Image:
    logo = Image.open(logo_path).convert("RGBA")
    height = round(logo.height * width / logo.width)
    return logo.resize((width, height), Image.Resampling.LANCZOS)


def _story_from_card(source: Path, target: Path, logo_path: Path, issue: str, index: int) -> None:
    canvas = Image.new("RGB", (1080, 1920), BG)
    draw = ImageDraw.Draw(canvas)
    logo = _fit_logo(logo_path, 230)
    canvas.paste(logo, (74, 58), logo)
    draw.text((1006, 82), f"ISSUE {issue}", font=_font("bold", 30), fill=INK, anchor="ra")

    card = Image.open(source).convert("RGB")
    card = ImageOps.contain(card, (900, 1125), Image.Resampling.LANCZOS)
    x = (1080 - card.width) // 2
    y = 190
    draw.rounded_rectangle((x - 5, y - 5, x + card.width + 5, y + card.height + 5), 10, fill=INK)
    canvas.paste(card, (x, y))

    cta = "Read Issue 001" if index % 2 else "Tap through for context"
    draw.text((90, 1400), cta, font=_font("serif", 61), fill=INK)
    draw.line((90, 1484, 990, 1484), fill=RED, width=8)
    draw.text((90, 1515), "Link sticker space", font=_font("bold", 25), fill="#6a6f78")
    canvas.save(target, "PNG", optimize=True)


def _launch_story(target: Path, logo_path: Path, issue: str) -> None:
    canvas = Image.new("RGB", (1080, 1920), BG)
    draw = ImageDraw.Draw(canvas)
    logo = _fit_logo(logo_path, 310)
    canvas.paste(logo, (80, 80), logo)
    draw.rectangle((0, 310, 1080, 1270), fill=INK)
    draw.rectangle((0, 310, 1080, 326), fill=RED)
    draw.text((82, 420), "K-SIGNAL", font=_font("bold", 72), fill=PAPER)
    draw.text((82, 530), f"Issue {issue} is live", font=_font("serif", 86), fill=PAPER)
    draw.multiline_text((82, 780), "What the internet\nis really saying.", font=_font("serif", 76), fill=PAPER, spacing=16)
    draw.text((82, 1110), "Four signals from Korean feeds this week.", font=_font("bold", 34), fill="#ffc928")
    draw.text((82, 1390), "Read Issue 001", font=_font("serif", 62), fill=INK)
    draw.line((82, 1476, 998, 1476), fill=RED, width=8)
    draw.text((82, 1510), "Link sticker space", font=_font("bold", 25), fill="#6a6f78")
    canvas.save(target, "PNG", optimize=True)


def _captions(url: str) -> str:
    return f"""A. Brand account launch caption

K-SIGNAL Issue 001 is live.

Four signals from Korean feeds this week:
— global K-pop fandom tension
— Billlie fans calling a rollout fumble
— K League fans building the starter pack
— Lingard bringing first-timers to FC Seoul

Korean feeds, translated with the context intact.

Read Issue 001:
{url}

Native Korean readers: if the read is off, correct us. That is part of the signal.


B. Card 01 caption

Global fandom loves K-pop. Korean fans aren’t so sure.

This thread gets messy fast: real frustration, ugly generalizing, and a trust gap that keeps getting louder.

Read the full signal:
{url}


C. Card 02 caption

Billlie fans think the obvious song got fumbled.

The internet is doing free A&R again. Fans think “Work” already has the heat.

Read the full signal:
{url}


D. Card 03 caption

K League fans made the starter pack first.

The league got curious outsiders. The fans built the front door.

Read the full signal:
{url}


E. Card 04 caption

Lingard brought new fans. Regulars wrote the manual.

This is what hype looks like after the headline: ticketing questions, stadium confusion, jersey prices, transit routes.

Read the full signal:
{url}
"""


def _dm_copy(url: str) -> str:
    return f"""A. Korean-native friend

Yo I’m testing Issue 001 of K-Signal — it turns Korean feed discourse into short visual cards/articles. Can you tell me if any Korean read feels off, unfair, or awkward?

{url}


B. Asian American friend

I’m testing this culture brief called K-Signal. It reads Korean internet discourse and turns it into quick visual cards. Which card actually hits?

{url}


C. K-pop friend

I made a test issue of K-Signal. The first two cards are K-pop/fandom related. Be honest — would either of these make you click or repost?

{url}


D. Soccer/K League friend

I made a test issue of K-Signal. The last two cards are about K League/Lingard. Tell me if this feels actually interesting or too niche.

{url}


E. General friend

I’m testing a new internet culture brief. Can you skim this and tell me which card hits hardest?

{url}
"""


REDDIT_PROMPTS = """A. r/kpopthoughts style

Title:
Are Korean fandom spaces and global K-pop fandom starting to want different things?

Body:
I’ve been looking at Korean fan-community reactions around international K-pop fandom, and one tension keeps coming up: global fans may love the idols/music while criticizing Korean fandom culture, the industry, or Korea itself. Korean-side threads sometimes read that as hostility rather than critique.

I’m curious if other people are seeing this split too. Is this a real fandom divide, or just loud comment-section weather?


B. Billlie / comeback discussion

Title:
Do fans sometimes spot the stronger comeback track before the agency does?

Body:
Billlie fans have been pushing “Work” as the track with more heat while “Zap” is the official title push. This feels like one of those moments where fandom starts doing free A&R in real time.

When do you think agencies should pivot toward the song fans are organically reacting to?


C. r/soccer / K League

Title:
Lingard to FC Seoul created a weirdly practical problem: onboarding new fans

Body:
One thing I found interesting about Lingard’s FC Seoul move is that Korean fans started writing practical guides for first-timers: tickets, seating, transit, jerseys, supporter sections.

It made me wonder whether clubs underestimate how much “how do I even attend?” content matters when a global name brings casual fans into a local league.
"""

POSTING_PLAN = """# K-Signal Issue 001 Posting Plan

## Day 1

- Create K-Signal IG account
- Post best card first, likely Card 02 or Card 04
- Story from personal account with link
- DM 5 people directly

## Day 2

- Post second card
- Story poll: “Would you read Issue 002?”
- DM 5 more people

## Day 3

- Post carousel or full issue recap
- Ask for Korean context corrections

## Day 4

- Reddit discussion post, no hard sell

## Day 5

- Post what readers corrected / what changed
"""

ACCOUNT_STRATEGY = """# Instagram Account Strategy

- Create a dedicated K-Signal brand account.
- Use personal account for initial trust and warm distribution.
- Brand account should host the actual posts.
- Personal account should repost stories, DM friends, and ask for feedback.
- Do not turn personal feed into the permanent product page.
- Early captions should say “testing Issue 001,” not pretend the brand is huge.
"""


def validate_distribution_pack(pack: Path) -> list[str]:
    errors: list[str] = []
    required = [
        pack / "ig_captions.txt", pack / "dm_sms_copy.txt", pack / "reddit_prompts.txt",
        pack / "outreach_tracker.csv", pack / "POSTING_PLAN.md", pack / "IG_ACCOUNT_STRATEGY.md",
    ]
    required += [pack / "ig_feed" / name for name in FEED_NAMES]
    required += [pack / "ig_story" / "00-issue-001-live.png"]
    required += [pack / "ig_story" / name for name in FEED_NAMES]
    for path in required:
        if not path.exists() or not path.is_file():
            errors.append(f"missing distribution asset: {path.name}")
    for path in (pack / "ig_feed").glob("*.png"):
        with Image.open(path) as image:
            if image.size != (1080, 1350):
                errors.append(f"{path.name} is not 1080x1350")
    for path in (pack / "ig_story").glob("*.png"):
        with Image.open(path) as image:
            if image.size != (1080, 1920):
                errors.append(f"{path.name} is not 1080x1920")
    return errors


def create_distribution_pack(issue: str, output_root: str | Path = "outputs/issues") -> tuple[Path, str, int]:
    issue_dir = Path(output_root) / issue
    social_dir = issue_dir / "social"
    logo_path = issue_dir / "assets" / "ksignal-logo.png"
    if not social_dir.exists() or not logo_path.exists():
        raise FileNotFoundError("Build the issue and export social cards before creating a distribution pack.")

    public_url = os.getenv("PUBLIC_ISSUE_URL", "").strip() or DEFAULT_PUBLIC_ISSUE_URL
    pack = issue_dir / "distribution_pack"
    if pack.exists():
        _remove_tree(pack)
    feed_dir = pack / "ig_feed"
    story_dir = pack / "ig_story"
    feed_dir.mkdir(parents=True)
    story_dir.mkdir(parents=True)

    for index, clean_name in enumerate(FEED_NAMES, 1):
        source = social_dir / f"card_{index:02d}.png"
        if not source.exists():
            raise FileNotFoundError(f"Missing social card: {source}")
        target = feed_dir / clean_name
        shutil.copy2(source, target)
        _story_from_card(source, story_dir / clean_name, logo_path, issue, index)
    _launch_story(story_dir / "00-issue-001-live.png", logo_path, issue)

    (pack / "ig_captions.txt").write_text(_captions(public_url), encoding="utf-8")
    (pack / "dm_sms_copy.txt").write_text(_dm_copy(public_url), encoding="utf-8")
    (pack / "reddit_prompts.txt").write_text(REDDIT_PROMPTS, encoding="utf-8")
    (pack / "POSTING_PLAN.md").write_text(POSTING_PLAN, encoding="utf-8")
    (pack / "IG_ACCOUNT_STRATEGY.md").write_text(ACCOUNT_STRATEGY, encoding="utf-8")

    with (pack / "outreach_tracker.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(("name", "audience_type", "platform", "sent_card", "sent_at", "responded", "response_quality", "notes", "follow_up_needed"))
        for audience in ("korean_native", "asian_american", "kpop", "sports", "general", "creator", "technical"):
            writer.writerow(("", audience, "", "", "", "", "", "", ""))

    from core.instagram_pack import create_instagram_pack
    create_instagram_pack(issue, output_root)

    errors = validate_distribution_pack(pack)
    if errors:
        raise ValueError("Distribution pack validation failed:\n- " + "\n- ".join(errors))
    return pack, public_url, len([path for path in pack.rglob("*") if path.is_file()])