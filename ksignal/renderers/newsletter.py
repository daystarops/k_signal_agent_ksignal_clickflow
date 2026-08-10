from __future__ import annotations

from pathlib import Path
from ksignal.schema import SignalCard
from ksignal.utils.files import ensure_dir


def render_markdown(cards: list[SignalCard], out_path: str | Path = "outputs/brief.md", title: str = "K Signal") -> str:
    lines: list[str] = []
    lines.append(f"# {title}\n")
    lines.append("_Korean-native internet signal, translated with visual context._\n")
    lines.append("**Lanes:** government · idols · sports · local phenomenon\n")

    visual_cards = [c for c in cards if c.image_paths or c.screenshot_paths]
    if visual_cards:
        lines.append("## Visual queue\n")
        for c in visual_cards[:12]:
            img = (c.image_paths or c.screenshot_paths)[0]
            rel = img.replace('outputs/', '') if img.startswith('outputs/') else img
            lines.append(f"### [{c.category}] {c.title_english or c.title_original}\n")
            lines.append(f"![visual]({rel})\n")
            if c.visual_read:
                lines.append(f"**Visual read:** {c.visual_read}\n")

    lines.append("## Signal cards\n")
    for i, c in enumerate(cards, 1):
        lines.append(f"### {i}. [{c.category}] {c.title_english or c.title_original}\n")
        lines.append(f"**Source:** {c.source}  ")
        if c.url:
            lines.append(f"**URL:** {c.url}  ")
        lines.append(f"**Confidence:** {c.confidence}\n")
        if c.raw_korean_excerpt:
            lines.append("**Raw Korean excerpt:**")
            lines.append(f"> {c.raw_korean_excerpt[:900]}\n")
        if c.literal_translation:
            lines.append(f"**Literal translation:** {c.literal_translation}\n")
        if c.cultural_read:
            lines.append(f"**Cultural read:** {c.cultural_read}\n")
        if c.business_read:
            lines.append(f"**Business read:** {c.business_read}\n")
        if c.translation_audit:
            lines.append(f"**Translation guardrail:** {c.translation_audit.translation_quality} / {c.translation_audit.quality_score}")
            if c.translation_audit.issues:
                lines.append(" — " + "; ".join(c.translation_audit.issues[:3]))
            lines.append("\n")
        if c.tags:
            lines.append("**Tags:** " + ", ".join(c.tags) + "\n")
        lines.append("---\n")

    out = "\n".join(lines)
    p = Path(out_path)
    ensure_dir(p.parent)
    p.write_text(out, encoding="utf-8")
    return out
