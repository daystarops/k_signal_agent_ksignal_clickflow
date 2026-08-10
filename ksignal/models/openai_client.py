from __future__ import annotations

import json
import os
from openai import OpenAI
from ksignal.schema import RawItem, SignalCard, VisionLayout, TranslationAudit
from ksignal.utils.images import image_file_to_data_url


def _translation_audit_from_json(output_text: str) -> TranslationAudit:
    """Parse guardrail JSON and tolerate richer issue objects from the model."""
    text = output_text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1]).strip()
    data = json.loads(text)
    issues = data.get("issues", [])
    if not isinstance(issues, list):
        issues = [issues]
    data["issues"] = [
        issue if isinstance(issue, str) else json.dumps(issue, ensure_ascii=False, sort_keys=True)
        for issue in issues
    ]
    return TranslationAudit(**data)


def _client() -> OpenAI | None:
    if not os.getenv("OPENAI_API_KEY"):
        return None
    return OpenAI()


def analyze_layout_with_vision(item: RawItem, screenshot_paths: list[str], visible_text_excerpt: str = "", model: str | None = None) -> VisionLayout:
    client = _client()
    if client is None or not screenshot_paths:
        return VisionLayout(
            page_type="unknown_no_api_or_screenshot",
            what_is_happening="No OpenAI key or screenshot provided, so vision analysis was skipped.",
            confidence="low",
        )
    model = model or os.getenv("OPENAI_VISION_MODEL", "gpt-5.5")
    content = [{"type": "input_text", "text": f"""
You are a Korean-native web culture layout analyst for a newsletter called K Signal.
The screenshot may be dense and may contain ads, nav, sidebars, app prompts, comment threads, ranking widgets, signup walls, and the actual post.

Analyze the screenshot as a human would see it. Do NOT just OCR everything. Separate main content from noise.

Return strict JSON matching this schema keys:
page_type, main_content_summary, main_content_region, comments_region, image_regions, ignore_regions, visible_images, likely_ads_or_ui, what_is_happening, confidence, notes.

Rules:
- Identify whether this is Naver Cafe, Naver News, Naver Blog, TheQoo, FM Korea, DCInside, search results, or unknown.
- Identify which images belong to the main post vs ads/sidebar/recommended content.
- Identify if the visible text is mostly comments, a post, a listing page, or a verification/paywall/join wall.
- Korean pages are dense: explicitly call out nearby ads, ranking widgets, and recommended links so the card writer does not confuse them with the post.
- Mention cultural context only if visibly supported.
- Keep it concise but useful for a newsletter editor.

Category target: {item.category}
Item title: {item.title}
Item source: {item.source}
URL: {item.url}
DOM/visible text excerpt: {visible_text_excerpt[:3500]}
"""}]
    for p in screenshot_paths[:3]:
        content.append({"type": "input_image", "image_url": image_file_to_data_url(p)})
    resp = client.responses.create(
        model=model,
        input=[{"role": "user", "content": content}],
        text={"format": {"type": "json_object"}},
    )
    try:
        data = json.loads(resp.output_text)
        return VisionLayout(**data)
    except Exception:
        return VisionLayout(what_is_happening=resp.output_text[:1200], confidence="medium")


def audit_translation(item: RawItem, card: SignalCard, model: str | None = None) -> TranslationAudit:
    client = _client()
    if client is None:
        return TranslationAudit(translation_quality="warn", quality_score=0, issues=["OPENAI_API_KEY missing"], notes="Skipped audit.")
    model = model or os.getenv("OPENAI_AUDIT_MODEL") or os.getenv("OPENAI_TEXT_MODEL", "gpt-5.5")
    prompt = f"""
You are a Korean-to-English translation QA editor. Audit the signal card for accuracy.

Return strict JSON matching keys:
source_language_confirmed, translation_quality, quality_score, issues, corrected_literal_translation, corrected_cultural_read, notes.

Rules:
- Compare the Korean excerpt/title/snippet with the English literal translation and cultural read.
- Flag mistranslations, missing negation, wrong subject, wrong platform context, hallucinated business implications, or confusing ads/comments/sidebar text as main content.
- If the source text is too thin to audit, mark warn and explain.
- If translation is acceptable, translation_quality=pass and quality_score >=80.
- If you can improve it materially, provide corrected_literal_translation and/or corrected_cultural_read.
- issues must be an array of short strings, never an array of objects.

Raw Korean source:
Title: {item.title}
Snippet: {item.snippet[:2000]}
Category: {item.category}
Source: {item.source}

Card:
{card.model_dump_json(indent=2)}
"""
    resp = client.responses.create(
        model=model,
        input=[{"role": "user", "content": [{"type": "input_text", "text": prompt}]}],
        text={"format": {"type": "json_object"}},
    )
    try:
        return _translation_audit_from_json(resp.output_text)
    except Exception:
        return TranslationAudit(translation_quality="warn", quality_score=50, issues=["Audit JSON parse failure"], notes=resp.output_text[:1000])


def create_signal_card(item: RawItem, vision: VisionLayout | None = None, model: str | None = None) -> SignalCard:
    client = _client()
    if client is None:
        return SignalCard(
            source=item.source,
            url=item.url,
            category=item.category,
            title_original=item.title,
            title_english="[OpenAI key missing]",
            raw_korean_excerpt=(item.snippet or item.title)[:800],
            literal_translation="Add OPENAI_API_KEY to generate translations.",
            cultural_read="Skipped.",
            business_read="Skipped.",
            visual_read=vision.what_is_happening if vision else "No vision analysis.",
            tags=["needs-api-key", item.category],
            confidence="low",
            image_paths=item.local_image_paths,
            screenshot_paths=item.screenshot_paths,
        )
    model = model or os.getenv("OPENAI_TEXT_MODEL", "gpt-5.5")
    vision_json = vision.model_dump() if vision else {}
    prompt = f"""
You are the editor of K Signal: a newsletter that translates Korean-native internet, fandom, sports, media, politics/government and local phenomena for English readers.

Create one clean signal card from this Korean item. Return strict JSON with keys:
source, url, category, title_original, title_english, raw_korean_excerpt, literal_translation, cultural_read, business_read, visual_read, tags, confidence.

Editorial standard:
- Write like an adult internet-native editor: sharp, socially observant, gossip-literate, and dryly funny when the source supports it.
- Choose one angle. Compress aggressively. A reader should understand the card on a phone in under 15 seconds.
- title_english is the headline: maximum 12 words.
- cultural_read is the hook/dek: maximum 140 characters. Do not repeat the headline.
- raw_korean_excerpt is one Korean receipt: maximum 180 characters.
- literal_translation is the paired English: maximum 220 characters.
- business_read is what the comments reveal about taste, status, anxiety, fandom, marketing, or public mood: maximum 280 characters. Treat comments as social weather, never truth.
- Avoid academic and consultant language. Never use stakeholders, operators should, this is a reminder that, leveraging insights, audience behavior, ecosystem, or content vertical.
- Allowed tonal moves include: fans are side-eyeing it; the comments are not buying it; the discourse gets messy; the internet is doing free consulting again; the agency may have fumbled the obvious play.
- Cover public discourse, not private lives. No private dating/sex rumors, body shaming, doxxing, medical or mental-health speculation, unverified allegations, harassment framing, or punching down.
- Never make blanket ethnic or national claims. If discourse is xenophobic, misogynistic, racist, or ugly, name the thread-specific tension without amplifying it as fact.
- Category must be exactly: government, idols, sports, local_phenomenon, or uncategorized.
- visual_read is internal evidence only. Distinguish main content from ads/comments/UI.
- If context is thin, say confidence low. Do not pretend an ad/sidebar/comment is the main story.

Raw item:
{item.model_dump_json(indent=2)}

Vision/layout context:
{json.dumps(vision_json, ensure_ascii=False, indent=2)}
"""
    resp = client.responses.create(
        model=model,
        input=[{"role": "user", "content": [{"type": "input_text", "text": prompt}]}],
        text={"format": {"type": "json_object"}},
    )
    try:
        data = json.loads(resp.output_text)
        data.setdefault("source", item.source)
        data.setdefault("url", item.url)
        data.setdefault("category", item.category)
        data.setdefault("title_original", item.title)
        data["image_paths"] = item.local_image_paths
        data["screenshot_paths"] = item.screenshot_paths
        card = SignalCard(**data)
    except Exception:
        card = SignalCard(
            source=item.source,
            url=item.url,
            category=item.category,
            title_original=item.title,
            title_english="Parse failure",
            raw_korean_excerpt=(item.snippet or item.title)[:800],
            literal_translation=resp.output_text[:1000],
            cultural_read="Could not parse model JSON.",
            business_read="Could not parse model JSON.",
            visual_read=vision.what_is_happening if vision else "",
            tags=["parse-failure", item.category],
            confidence="low",
            image_paths=item.local_image_paths,
            screenshot_paths=item.screenshot_paths,
        )

    if os.getenv("TRANSLATION_GUARDRAIL", "true").lower() != "false":
        audit = audit_translation(item, card)
        card.translation_audit = audit
        if audit.corrected_literal_translation:
            card.literal_translation = audit.corrected_literal_translation
        if audit.corrected_cultural_read:
            card.cultural_read = audit.corrected_cultural_read
        if audit.translation_quality == "fail" or audit.quality_score < 70:
            card.confidence = "low"
        elif audit.translation_quality == "warn" and card.confidence == "high":
            card.confidence = "medium"
    return card
