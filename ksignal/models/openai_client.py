from __future__ import annotations

import json
import os
from typing import TypeVar
from openai import OpenAI
from pydantic import BaseModel, ConfigDict
from ksignal.schema import RawItem, SignalCard, VisionLayout, TranslationAudit
from ksignal.utils.images import image_file_to_data_url


class TranslationOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    literal_translation: str
    natural_translation: str


class KoreanNuanceOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    korean_nuance_read: str
    cultural_read: str


class BusinessReadOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    business_read: str


StructuredOutput = TypeVar("StructuredOutput", bound=BaseModel)


def _structured_response(
    client,
    *,
    model: str,
    prompt: str,
    output_type: type[StructuredOutput],
) -> StructuredOutput:
    response = client.responses.parse(
        model=model,
        input=[{"role": "user", "content": [{"type": "input_text", "text": prompt}]}],
        text_format=output_type,
    )
    if response.output_parsed is None:
        raise ValueError("Structured response did not contain parsed output")
    return response.output_parsed


def translate_source_text(item: RawItem, model: str | None = None) -> TranslationOutput:
    """Translate original Korean faithfully and naturally, without interpretation."""
    # Revalidate mutable legacy instances at the language boundary so provenance
    # cannot be corrupted after initial construction.
    item = RawItem.model_validate(item.model_dump())
    client = _client()
    if client is None:
        return TranslationOutput(
            literal_translation="Add OPENAI_API_KEY to generate translations.",
            natural_translation="Add OPENAI_API_KEY to generate translations.",
        )
    model = model or os.getenv("OPENAI_TEXT_MODEL", "gpt-5.5")
    prompt = f"""
You are performing Korean-to-English translation only.
Return strict JSON containing exactly: literal_translation, natural_translation.

literal_translation must be faithful English. Preserve who did what, chronology,
numbers, quoted wording, uncertainty, and named entities. Do not summarize,
editorialize, add cultural interpretation, or add trend or business analysis.

natural_translation must be fluent publication-quality English with exactly the
same facts and certainty. It may remove awkward Korean-news syntax and resolve an
obvious implied subject only when the source establishes it. Do not invent context,
strengthen claims, or make neutral wording emotional.

Original Korean source (authoritative):
Title: {item.title}
Snippet/excerpt: {item.snippet[:4000]}
Source: {item.source}
Category: {item.category}
Published at: {item.published_at or ""}
URL: {item.url}
"""
    return _structured_response(
        client, model=model, prompt=prompt, output_type=TranslationOutput
    )


def review_korean_nuance(
    item: RawItem,
    translation: TranslationOutput,
    model: str | None = None,
) -> KoreanNuanceOutput:
    """Review English translations against the authoritative original Korean."""
    client = _client()
    if client is None:
        return KoreanNuanceOutput(korean_nuance_read="Skipped.", cultural_read="Skipped.")
    model = model or os.getenv("OPENAI_TEXT_MODEL", "gpt-5.5")
    prompt = f"""
You are a Korean-language nuance reviewer. The original Korean is authoritative.
Evaluate both English versions against it; never translate the English back into Korean.
Return strict JSON containing exactly: korean_nuance_read, cultural_read.

korean_nuance_read is a concise editor-facing note limited to material implied
subjects, idioms, slang, newsroom shorthand, register, speaker attitude,
culturally meaningful phrasing, ambiguity, flattened meaning, or places where a
literal English reading could mislead.

cultural_read is 1-3 concise, natural, conversational sentences answering:
"What would a fluent Korean reader actually hear or understand here that a
literal English translation might not communicate?"

Do not provide business opportunity analysis, trend scoring, propagation claims,
evidence sufficiency, PASS/HOLD/FAIL language, or article writing.

Original Korean title: {item.title}
Original Korean snippet/excerpt: {item.snippet[:4000]}
Faithful English (literal_translation): {translation.literal_translation}
Natural English (natural_translation): {translation.natural_translation}
Source: {item.source}
Category: {item.category}
"""
    return _structured_response(
        client, model=model, prompt=prompt, output_type=KoreanNuanceOutput
    )


def create_business_read(
    item: RawItem,
    translation: TranslationOutput,
    nuance: KoreanNuanceOutput,
    vision: VisionLayout | None = None,
    model: str | None = None,
) -> BusinessReadOutput:
    """Create only the downstream signal/business interpretation."""
    client = _client()
    if client is None:
        return BusinessReadOutput(business_read="Skipped.")
    model = model or os.getenv("OPENAI_TEXT_MODEL", "gpt-5.5")
    vision_json = vision.model_dump() if vision else {}
    prompt = f"""
You are producing only the concise business/signal read for a K Signal card.
Return strict JSON containing exactly: business_read.

Explain only what the supplied source and language review reveal about taste,
status, anxiety, fandom, marketing, or public mood. Treat comments as social
weather, never truth. Do not regenerate either translation, rewrite the cultural
read, perform evidence PASS/HOLD/FAIL logic, or write an article. Do not invent a
business implication when context is thin; an empty string is acceptable. Avoid
"This highlights", "The broader implication", and "The evidence suggests" unless
the source itself uses that framing. Maximum 280 characters.

Original Korean title: {item.title}
Original Korean snippet/excerpt: {item.snippet[:4000]}
Faithful English (literal_translation): {translation.literal_translation}
Natural English (natural_translation): {translation.natural_translation}
Korean nuance (korean_nuance_read): {nuance.korean_nuance_read}
Conversational read (cultural_read): {nuance.cultural_read}
Source metadata: source={item.source}; category={item.category}; url={item.url}
Vision/layout context: {json.dumps(vision_json, ensure_ascii=False)}
"""
    return _structured_response(
        client, model=model, prompt=prompt, output_type=BusinessReadOutput
    )


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
source_language_confirmed, translation_quality, quality_score, issues,
corrected_literal_translation, corrected_natural_translation,
corrected_korean_nuance_read, corrected_cultural_read, notes.

Rules:
- Treat the original Korean title/snippet as authoritative. Compare it with the
  faithful translation, natural translation, Korean nuance note, and cultural read.
- Flag mistranslations, missing negation, wrong subject, wrong platform context,
  flattened material nuance, or confusing ads/comments/sidebar text as main content.
- If the source text is too thin to audit, mark warn and explain.
- If translation is acceptable, translation_quality=pass and quality_score >=80.
- If materially needed, provide corrections for any of the four language fields.
- Do not modify or correct business_read, evidence state, or scores outside this audit.
- issues must be an array of short strings, never an array of objects.

Raw Korean source:
Title: {item.title}
Snippet: {item.snippet[:2000]}
Category: {item.category}
Source: {item.source}

Card:
{card.model_dump_json(indent=2)}
"""
    try:
        return _structured_response(
            client, model=model, prompt=prompt, output_type=TranslationAudit
        )
    except Exception:
        return TranslationAudit(translation_quality="warn", quality_score=50, issues=["Audit JSON parse failure"])


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
            natural_translation="Add OPENAI_API_KEY to generate translations.",
            korean_nuance_read="Skipped.",
            cultural_read="Skipped.",
            business_read="Skipped.",
            visual_read=vision.what_is_happening if vision else "No vision analysis.",
            tags=["needs-api-key", item.category],
            confidence="low",
            image_paths=item.local_image_paths,
            screenshot_paths=item.screenshot_paths,
        )
    model = model or os.getenv("OPENAI_TEXT_MODEL", "gpt-5.5")
    try:
        translation = translate_source_text(item, model=model)
        nuance = review_korean_nuance(item, translation, model=model)
        business = create_business_read(item, translation, nuance, vision=vision, model=model)
        card = SignalCard(
            source=item.source,
            url=item.url,
            category=item.category,
            title_original=item.title,
            title_english=translation.natural_translation,
            raw_korean_excerpt=(item.snippet or item.title)[:180],
            literal_translation=translation.literal_translation,
            natural_translation=translation.natural_translation,
            korean_nuance_read=nuance.korean_nuance_read,
            cultural_read=nuance.cultural_read,
            business_read=business.business_read,
            visual_read=vision.what_is_happening if vision else "",
            tags=[item.category],
            confidence=vision.confidence if vision else "medium",
            image_paths=item.local_image_paths,
            screenshot_paths=item.screenshot_paths,
        )
    except Exception:
        card = SignalCard(
            source=item.source,
            url=item.url,
            category=item.category,
            title_original=item.title,
            title_english="Parse failure",
            raw_korean_excerpt=(item.snippet or item.title)[:800],
            literal_translation="Language intelligence response parse failure.",
            natural_translation="Language intelligence response parse failure.",
            korean_nuance_read="Could not parse model JSON.",
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
        if audit.corrected_natural_translation:
            card.natural_translation = audit.corrected_natural_translation
        if audit.corrected_korean_nuance_read:
            card.korean_nuance_read = audit.corrected_korean_nuance_read
        if audit.corrected_cultural_read:
            card.cultural_read = audit.corrected_cultural_read
        if audit.translation_quality == "fail" or audit.quality_score < 70:
            card.confidence = "low"
        elif audit.translation_quality == "warn" and card.confidence == "high":
            card.confidence = "medium"
    return card
