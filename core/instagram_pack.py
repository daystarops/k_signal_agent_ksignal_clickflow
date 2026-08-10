from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

from core.creative_scout import scout_creatives, write_creative_sources
from core.instagram_reels import render_reels

DEFAULT_URL = "https://read-ksignal.netlify.app/"
FEED_SIZE, STORY_SIZE = (1080, 1350), (1080, 1920)
BG, PAPER, INK, RED, YELLOW, GRAY = "#e6e1d6", "#f5f0e4", "#101828", "#ef3f36", "#ffc928", "#667085"
META = (
    ("card_01_global_kpop", "The fandom split is the story.", "Does this read feel fair?", "K-pop, Korean-native, diaspora, and culture readers", "Carousel after context-check", "Post only after Korean-native feedback says the framing is fair", "High — sensitive fandom/nationality tension", "7–9 PM", "Framing corrections; whether readers see critique, hostility, or both", "Essential"),
    ("card_02_billlie", "The internet is doing free A&R again.", "Did the agency fumble it?", "K-pop fans, comeback watchers, and music-marketing readers", "Carousel first; reel frames as follow-up", "Recommended first K-pop post", "Low–medium — critique the rollout, not individuals", "6–9 PM", "Whether fans agree “Work” has organic heat", "Helpful, especially from Billlie fans"),
    ("card_03_kleague_starter", "Fans built the front door before the league did.", "Is this actually useful?", "K League, football, sports-business, and expat readers", "Smart explainer carousel", "Niche-but-sharp proof of K-Signal’s range", "Low", "Noon–2 PM or 6–8 PM", "Whether newcomers want practical guides", "Recommended from K League regulars"),
    ("card_04_lingard_fcseoul", "Hype creates customer-service problems.", "Would this get you to a match?", "Football, Premier League, K League, and general culture readers", "Carousel first; strong story sequence", "Recommended first sports/general post", "Low", "5–8 PM", "Ticket, transit, seating, jersey, and first-match questions", "Helpful from FC Seoul regulars"),
)


def font(kind: str, size: int):
    paths = {
        "bold": ("C:/Windows/Fonts/malgunbd.ttf", "C:/Windows/Fonts/arialbd.ttf"),
        "regular": ("C:/Windows/Fonts/malgun.ttf", "C:/Windows/Fonts/arial.ttf"),
        "serif": ("C:/Windows/Fonts/georgiab.ttf", "C:/Windows/Fonts/malgunbd.ttf"),
    }
    for path in paths[kind]:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def wrap(draw, text, used_font, width, max_lines=7):
    words, lines, current = str(text).replace("\n", " \n ").split(), [], ""
    for word in words:
        if word == "\n":
            if current:
                lines.append(current)
                current = ""
            continue
        candidate = f"{current} {word}".strip()
        if not current or draw.textlength(candidate, font=used_font) <= width:
            current = candidate
        else:
            lines.append(current)
            current = word
        if len(lines) >= max_lines:
            break
    if current and len(lines) < max_lines:
        lines.append(current)
    if len(lines) == max_lines and len(" ".join(lines)) < len(str(text)):
        lines[-1] = lines[-1].rstrip("., ") + "…"
    return lines


def text_block(draw, x, y, text, used_font, fill, width, max_lines=7, spacing=10):
    box = draw.textbbox((0, 0), "Ag", font=used_font)
    line_h = box[3] - box[1]
    for line in wrap(draw, text, used_font, width, max_lines):
        draw.text((x, y), line, font=used_font, fill=fill)
        y += line_h + spacing
    return y


def fit(path, size):
    return ImageOps.fit(Image.open(path).convert("RGB"), size, Image.Resampling.LANCZOS)


def brand(canvas, logo_path, issue):
    logo = Image.open(logo_path).convert("RGBA")
    logo.thumbnail((200, 80), Image.Resampling.LANCZOS)
    canvas.paste(logo, (60, 45), logo)
    ImageDraw.Draw(canvas).text((canvas.width - 60, 63), f"ISSUE {issue}", font=font("bold", 25), fill=INK, anchor="ra")


def lane(draw, value, y):
    f = font("bold", 23)
    width = draw.textlength(value.upper(), font=f) + 36
    draw.rounded_rectangle((60, y, 60 + width, y + 48), 24, fill=RED)
    draw.text((78, y + 10), value.upper(), font=f, fill="white")


def new_canvas(size, color=BG):
    return Image.new("RGB", size, color)


def carousel_slides(card, meta, hero, source, logo, issue, url, folder):
    folder.mkdir(parents=True, exist_ok=True)
    consequence = meta[1]

    c = new_canvas(FEED_SIZE, PAPER); c.paste(fit(hero, (1080, 700)), (0, 0)); d = ImageDraw.Draw(c); brand(c, logo, issue); lane(d, card["lane"], 750)
    y = text_block(d, 60, 830, card["title"], font("serif", 58), INK, 950, 3)
    text_block(d, 60, y + 18, card["heard_in_feed"], font("bold", 32), INK, 950, 3)
    c.save(folder / "slide_01_hook.png")

    c = new_canvas(FEED_SIZE); d = ImageDraw.Draw(c); brand(c, logo, issue); d.text((60, 160), "The receipt", font=font("serif", 56), fill=INK)
    shot = ImageOps.contain(Image.open(source).convert("RGB"), (900, 760), Image.Resampling.LANCZOS); x = (1080 - shot.width) // 2; c.paste(shot, (x, 250))
    d.text((60, 1050), "KOREAN SOURCE", font=font("bold", 22), fill=RED); text_block(d, 60, 1100, card["korean_quote"], font("bold", 28), INK, 950, 3)
    c.save(folder / "slide_02_receipt.png")

    c = new_canvas(FEED_SIZE, PAPER); d = ImageDraw.Draw(c); brand(c, logo, issue); d.text((60, 160), "In English", font=font("serif", 60), fill=INK)
    d.rounded_rectangle((50, 270, 1030, 700), 20, fill=BG); d.text((85, 305), "KOREAN", font=font("bold", 22), fill=RED)
    text_block(d, 85, 355, card["korean_quote"], font("bold", 30), INK, 900, 6)
    d.line((60, 755, 1020, 755), fill=INK, width=2); d.text((85, 815), "IN ENGLISH", font=font("bold", 22), fill=RED)
    text_block(d, 85, 870, card["english_translation"], font("serif", 40), INK, 900, 6)
    c.save(folder / "slide_03_in_english.png")

    c = new_canvas(FEED_SIZE, INK); d = ImageDraw.Draw(c); brand(c, logo, issue)
    d.text((60, 210), "WHAT THE INTERNET IS REALLY SAYING", font=font("bold", 25), fill=YELLOW)
    text_block(d, 60, 350, card["comments_read"], font("serif", 52), PAPER, 950, 7, 15); d.rectangle((60, 1160, 1020, 1170), fill=RED)
    c.save(folder / "slide_04_internet_read.png")

    c = new_canvas(FEED_SIZE, RED); d = ImageDraw.Draw(c); brand(c, logo, issue); d.text((60, 260), "THE CHANGE", font=font("bold", 26), fill=INK)
    text_block(d, 60, 370, consequence, font("serif", 76), "white", 950, 5, 18); d.text((60, 1140), "That’s the signal.", font=font("bold", 30), fill=INK)
    c.save(folder / "slide_05_the_change.png")

    c = new_canvas(FEED_SIZE, INK); d = ImageDraw.Draw(c); brand(c, logo, issue); c.paste(fit(hero, (940, 900)), (70, 180))
    if card.get("media_type") == "video" and card.get("video_click_url"):
        d.ellipse((465, 555, 615, 705), fill=RED); d.polygon(((525, 593), (525, 667), (585, 630)), fill="white")
    d.text((70, 1120), "CONTEXT FRAME", font=font("bold", 23), fill=YELLOW)
    text_block(d, 70, 1170, card.get("hero_caption") or "Visual receipt from the source page.", font("bold", 27), PAPER, 930, 2)
    c.save(folder / "slide_06_context.png")

    c = new_canvas(FEED_SIZE); d = ImageDraw.Draw(c); brand(c, logo, issue)
    y = text_block(d, 60, 320, "Read the full signal", font("serif", 84), INK, 950, 3); d.rectangle((60, y + 40, 1020, y + 50), fill=RED)
    text_block(d, 60, y + 110, url, font("bold", 29), INK, 950, 3); d.text((60, 1080), "Correct us if the read is off.", font=font("bold", 31), fill=INK)
    c.save(folder / "slide_07_read_full_signal.png")


def story_frames(card, meta, hero, source, logo, issue, url, folder):
    folder.mkdir(parents=True, exist_ok=True)
    poll = meta[2]
    for number in range(1, 6):
        c = new_canvas(STORY_SIZE); d = ImageDraw.Draw(c); brand(c, logo, issue)
        if number == 1:
            c.paste(fit(hero, (1080, 920)), (0, 180)); d.rectangle((0, 1100, 1080, 1920), fill=PAPER); lane(d, card["lane"], 1160)
            y = text_block(d, 65, 1250, card["title"], font("serif", 65), INK, 950, 4, 12)
            text_block(d, 65, y + 20, card["heard_in_feed"], font("bold", 33), INK, 950, 3)
        elif number == 2:
            d.text((65, 180), "The receipt", font=font("serif", 64), fill=INK)
            shot = ImageOps.contain(Image.open(source).convert("RGB"), (930, 1100), Image.Resampling.LANCZOS); c.paste(shot, ((1080 - shot.width) // 2, 300))
            text_block(d, 65, 1480, card["korean_quote"], font("bold", 29), INK, 950, 4)
        elif number == 3:
            d.text((65, 190), "In English", font=font("serif", 68), fill=INK); d.text((65, 350), "KOREAN", font=font("bold", 23), fill=RED)
            y = text_block(d, 65, 410, card["korean_quote"], font("bold", 32), INK, 950, 7)
            d.line((65, y + 40, 1015, y + 40), fill=RED, width=7); d.text((65, y + 100), "IN ENGLISH", font=font("bold", 23), fill=RED)
            text_block(d, 65, y + 160, card["english_translation"], font("serif", 43), INK, 950, 7, 13)
        elif number == 4:
            d.rectangle((0, 170, 1080, 1920), fill=INK); d.text((65, 280), "YOUR READ?", font=font("bold", 27), fill=YELLOW)
            text_block(d, 65, 390, poll, font("serif", 74), PAPER, 950, 5, 16)
            for y, label, fill, color in ((960, "FAIR", PAPER, INK), (1140, "NEEDS CONTEXT", RED, "white")):
                d.rounded_rectangle((90, y, 990, y + 125), 62, fill=fill); d.text((540, y + 39), label, font=font("bold", 34), fill=color, anchor="ma")
            d.text((90, 1470), "Add Instagram’s poll sticker here.", font=font("regular", 27), fill="#b7bdc7")
        else:
            d.text((65, 290), "Read the full signal", font=font("serif", 76), fill=INK); d.line((65, 420, 1015, 420), fill=RED, width=8)
            text_block(d, 65, 500, url, font("bold", 31), INK, 950, 4)
            d.rounded_rectangle((130, 920, 950, 1120), 100, outline=INK, width=4); d.text((540, 984), "LINK STICKER", font=font("bold", 35), fill=INK, anchor="ma")
            d.text((65, 1370), "Korean readers: fair or off?", font=font("serif", 47), fill=INK)
        c.save(folder / f"story_{number:02d}.png")


def reel_frames(card, meta, hero, source, logo, issue, url, folder):
    folder.mkdir(parents=True, exist_ok=True)
    blocks = (("HEADLINE", card["title"], card["heard_in_feed"]), ("THE RECEIPT", card["korean_quote"], ""), ("IN ENGLISH", card["english_translation"], meta[1]), ("READ THE FULL SIGNAL", url, "Context-first. Receipts included."))
    for index, (label, main, sub) in enumerate(blocks, 1):
        dark = index in (1, 3); c = new_canvas(STORY_SIZE, INK if dark else BG); d = ImageDraw.Draw(c)
        if index == 1:
            c.paste(fit(hero, (1080, 850)), (0, 180)); d.rectangle((0, 1030, 1080, 1920), fill=INK)
        elif index == 2:
            shot = ImageOps.contain(Image.open(source).convert("RGB"), (930, 900), Image.Resampling.LANCZOS)
            c.paste(shot, ((1080 - shot.width) // 2, 690))
        brand(c, logo, issue); color, accent = (PAPER, YELLOW) if dark else (INK, RED); top = 1120 if index == 1 else 310
        d.text((65, top), label, font=font("bold", 28), fill=accent)
        y = text_block(d, 65, top + 80, main, font("bold" if index == 2 else "serif", 39 if index == 2 else 61), color, 950, 7, 14)
        if sub:
            text_block(d, 65, y + 45, sub, font("bold", 31), color, 950, 4)
        c.save(folder / f"frame_{index:02d}.png")
    (folder / "reel_script.txt").write_text("00:00–00:02 Headline\n00:02–00:05 Hero/source still with subtle pan or zoom\n00:05–00:07 Korean quote\n00:07–00:10 English translation and consequence\n00:10–00:12 Read the full signal\n\nSilent-friendly; burned-in captions; no copyrighted audio or downloaded source video.\n", encoding="utf-8")


def captions(card, meta, url):
    return f"""1. Feed carousel caption

{card['title']}

{card['comments_read']}

{meta[1]}

Read the full signal ↓
{url}


2. Story caption / text stickers

Hook: {card['heard_in_feed']}
Receipt: The receipt
Translation: In English
Poll: {meta[2]}
Link sticker: Read Issue 001 — {url}


3. Reel caption

{card['title']}
{meta[1]}

Full context and receipts:
{url}


4. Comment pin suggestion

The comments are social weather, not settled fact. Korean readers: if this framing is off, correct it here.


5. DM prompt

I’m testing this K-Signal post before it goes wider. Does the framing land, and which slide would make you keep swiping?

{url}
"""


def posting_notes(meta):
    return f"""# Posting Notes

- **Best audience:** {meta[3]}
- **Best format:** {meta[4]}
- **Best first-post use:** {meta[5]}
- **Risk level:** {meta[6]}
- **Suggested posting time:** {meta[7]}
- **Response to watch:** {meta[8]}
- **Korean context-check:** {meta[9]}
- **Link sticker:** Put PUBLIC_ISSUE_URL on the final story frame, centered in the reserved box.
- **Rights note:** Motion assets use original K-Signal layouts and approved still/source screenshots only. No source video or music is downloaded.
"""


POST_ORDER = """# Issue 001 Instagram Post Order

## Day 1
- Post Card 02 carousel first
- Story poll from personal account
- DM 5 K-pop/Korean friends

## Day 2
- Post Card 04 carousel
- Story link sticker
- DM 5 sports/general friends

## Day 3
- Post Card 01 only if Korean-native feedback says the framing is fair
- Ask for corrections publicly

## Day 4
- Post Card 03
- Try Reddit discussion, no link spam

## Day 5
- Post “what readers corrected” story
"""


def try_mp4(folder):
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return False
    result = subprocess.run([ffmpeg, "-y", "-framerate", "0.4", "-i", str(folder / "frame_%02d.png"), "-vf", "fps=30,format=yuv420p", "-t", "10", "-movflags", "+faststart", str(folder / "reel_01.mp4")], capture_output=True)
    return result.returncode == 0 and (folder / "reel_01.mp4").exists()


def create_instagram_pack(issue: str, output_root: str | Path = "outputs/issues", allow_unknown_rights: bool = False, mode: str = "creator_mode"):
    issue_dir = Path(output_root) / issue
    cards = json.loads((issue_dir / "editorial_cards.json").read_text(encoding="utf-8"))
    if len(cards) != 4:
        raise ValueError("Issue 001 Instagram pack expects four cards.")
    url = os.getenv("PUBLIC_ISSUE_URL", "").strip() or DEFAULT_URL
    root = issue_dir / "distribution_pack" / "instagram"
    root.mkdir(parents=True, exist_ok=True)
    manifest, _, _ = scout_creatives(issue, output_root, allow_unknown_rights, mode=mode)
    write_creative_sources(manifest, root / "CREATIVE_SOURCES.md")
    logo = issue_dir / "assets" / "ksignal-logo.png"
    master, any_mp4 = [], False
    for index, (card, meta) in enumerate(zip(cards, META), 1):
        card_root = root / meta[0]
        carousel, stories, reels = card_root / "carousel", card_root / "stories", card_root / "reels"
        hero = issue_dir / "media" / f"card_{index:02d}_hero{Path(card['hero_image_path']).suffix}"
        source = issue_dir / "media" / f"card_{index:02d}_source.png"
        carousel_slides(card, meta, hero, source, logo, issue, url, carousel)
        story_frames(card, meta, hero, source, logo, issue, url, stories)
        reel_frames(card, meta, hero, source, logo, issue, url, reels)
        copy = captions(card, meta, url)
        (card_root / "captions.txt").write_text(copy, encoding="utf-8")
        (card_root / "posting_notes.md").write_text(posting_notes(meta), encoding="utf-8")
        master += [f"===== CARD {index:02d}: {card['title']} =====", "", copy, ""]
    (root / "POST_ORDER.md").write_text(POST_ORDER, encoding="utf-8")
    (root / "MASTER_CAPTIONS.txt").write_text("\n".join(master), encoding="utf-8")
    reel_results = render_reels(issue, output_root)
    any_mp4 = all(item["success"] for item in reel_results)

    errors = []
    for meta in META:
        card_root = root / meta[0]
        groups = ((card_root / "carousel", 7, FEED_SIZE, "*.png"), (card_root / "stories", 5, STORY_SIZE, "*.png"), (card_root / "reels", 4, STORY_SIZE, "frame_*.png"))
        for folder, expected, size, pattern in groups:
            files = sorted(folder.glob(pattern))
            if len(files) != expected:
                errors.append(f"{meta[0]}/{folder.name}: expected {expected} images")
            for path in files:
                with Image.open(path) as image:
                    if image.size != size:
                        errors.append(f"{path}: wrong dimensions")
        for name in ("captions.txt", "posting_notes.md"):
            if not (card_root / name).exists():
                errors.append(f"{meta[0]}: missing {name}")
        if not (card_root / "reels" / "reel_01.mp4").exists() and not (card_root / "reels" / "reel_script.txt").exists():
            errors.append(f"{meta[0]}: missing reel output")
    if errors:
        raise ValueError("Instagram pack validation failed:\n- " + "\n- ".join(errors))
    return root, url, len([p for p in root.rglob("*") if p.is_file()]), any_mp4