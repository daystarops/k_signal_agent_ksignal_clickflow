"""Build integration and HTML rendering for article discovery."""
from __future__ import annotations

from html import escape
import json
from pathlib import Path
import re
from typing import Any

from .relevance import enrich_card, more_from_issue, related_signals

DISCOVERY_CSS = r"""
.discovery{margin-top:34px}.discovery-section{border-top:2px solid var(--navy);padding-top:18px;margin-top:28px}.discovery-section>h2{font:700 22px/1.2 Georgia,serif;margin:0 0 16px}.related-signals-list{display:grid;grid-template-columns:1fr 1fr;gap:12px}.related-signal-card{display:grid;grid-template-columns:88px 1fr;gap:13px;padding:13px;border:1px solid var(--line);color:var(--navy);text-decoration:none;min-width:0}.related-signal-card.no-image{grid-template-columns:1fr}.discovery-thumb{width:88px;height:70px;object-fit:cover;background:#e7e9ec}.discovery-meta{color:var(--red);font-size:10px;font-weight:800;letter-spacing:.03em}.related-signal-card h3,.issue-signal-card h3{font:700 16px/1.18 Georgia,serif;margin:6px 0}.related-signal-card p{color:var(--muted);font-size:12px;line-height:1.4;margin:0}.discovery-read{display:block;margin-top:9px;font-size:11px;font-weight:800;text-decoration:underline;text-underline-offset:3px}.issue-signal-strip{display:flex;gap:10px;overflow-x:auto;overscroll-behavior-inline:contain;scroll-snap-type:x proximity;padding:1px 1px 9px;max-width:100%}.issue-signal-card{display:grid;grid-template-columns:64px minmax(150px,1fr);gap:10px;flex:1 0 220px;max-width:290px;scroll-snap-align:start;padding:10px;border:1px solid var(--line);color:var(--navy);text-decoration:none}.issue-signal-card .discovery-thumb{width:64px;height:54px}.issue-signal-card h3{font-size:14px;margin-bottom:0}@media(max-width:760px){.related-signals-list{grid-template-columns:1fr}.related-signal-card{grid-template-columns:72px 1fr}.related-signal-card .discovery-thumb{width:72px;height:62px}.issue-signal-strip{-webkit-overflow-scrolling:touch;touch-action:pan-x pan-y}.issue-signal-card{flex-basis:82%;max-width:270px}}
"""

def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default

def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

def _img(card: dict[str, Any]) -> str:
    image = card.get("thumbnail") or card.get("hero_image")
    if not image:
        return ""
    name = Path(str(image).replace("\\", "/")).name
    return f'<img class="discovery-thumb" src="../media/{escape(name, quote=True)}" alt="" loading="lazy">'

def _render_related(cards: list[dict[str, Any]]) -> str:
    rendered = []
    for card in cards:
        summary, image = card.get("public_summary") or card.get("dek") or "", _img(card)
        rendered.append(f'<a class="related-signal-card{"" if image else " no-image"}" data-related-card-id="{escape(str(card.get("card_id")), quote=True)}" href="{escape(Path(str(card.get("article_path"))).name, quote=True)}">{image}<div><div class="discovery-meta">{escape(str(card.get("lane_label") or card.get("lane") or ""))} · Issue {escape(str(card.get("issue_id") or ""))}</div><h3>{escape(str(card.get("headline") or ""))}</h3><p>{escape(str(summary))}</p><span class="discovery-read">Read the signal →</span></div></a>')
    return '<section class="discovery-section related-signals" aria-labelledby="related-signals-title"><h2 id="related-signals-title">Related signals</h2><div class="related-signals-list">' + "".join(rendered) + "</div></section>"

def _render_issue(issue: str, cards: list[dict[str, Any]]) -> str:
    rendered = []
    for card in cards:
        rendered.append(f'<a class="issue-signal-card" data-issue-card-id="{escape(str(card.get("card_id")), quote=True)}" data-editorial-order="{escape(str(card.get("editorial_order")), quote=True)}" href="{escape(Path(str(card.get("article_path"))).name, quote=True)}">{_img(card)}<div><div class="discovery-meta">{escape(str(card.get("lane_label") or card.get("lane") or ""))}</div><h3>{escape(str(card.get("headline") or ""))}</h3></div></a>')
    title = f"More from Issue {issue}"
    return f'<section class="discovery-section more-from-issue" aria-labelledby="more-from-issue-title"><h2 id="more-from-issue-title">{escape(title)}</h2><div class="issue-signal-strip" tabindex="0" aria-label="{escape(title, quote=True)}">' + "".join(rendered) + "</div></section>"

def _augment_article(path: Path, related: list[dict[str, Any]], issue_cards: list[dict[str, Any]], issue: str) -> None:
    html = path.read_text(encoding="utf-8")
    html = re.sub(r'<section class="related">.*?</section>', '', html, count=1, flags=re.S)
    block = f'<div class="discovery" data-pagefind-ignore>{_render_related(related)}{_render_issue(issue, issue_cards)}</div>'
    html = html.replace("</main>", block + "</main>", 1).replace("</style>", DISCOVERY_CSS + "</style>", 1)
    path.write_text(html, encoding="utf-8")

def build_discovery(issue_dir: str | Path, issue: str) -> None:
    issue_dir = Path(issue_dir)
    index_path = issue_dir / "search" / "cards_index.json"
    cards, editorial = _read_json(index_path, []), _read_json(issue_dir / "editorial_cards.json", [])
    by_slug = {item.get("article_slug"): item for item in editorial}
    warnings, enriched = [], []
    for order, card in enumerate(cards, 1):
        source, merged = by_slug.get(card.get("card_id"), {}), dict(card)
        merged.setdefault("source_url", source.get("source_url") or source.get("url"))
        merged.setdefault("source_board", source.get("source"))
        merged.setdefault("translation_status", "translated" if merged.get("english_translation") else "not_recorded")
        merged.setdefault("access_status", "public" if source.get("publishable") else "not_recorded")
        merged = enrich_card(merged, order)
        missing = [field for field in ("captured_at", "source_board", "source_url") if not merged.get(field)]
        if missing: warnings.append(f"{merged.get('card_id')}: missing {', '.join(missing)}")
        enriched.append(merged)
    _write_json(index_path, enriched)
    global_path = issue_dir.parents[1] / "search" / "cards_index.json"
    global_cards = _read_json(global_path, [])
    if global_cards:
        replacements = {(c["issue_id"], c["card_id"]): c for c in enriched}
        global_cards = [replacements.get((c.get("issue_id"), c.get("card_id")), c) for c in global_cards]
        _write_json(global_path, global_cards)
    archive, overrides = global_cards or enriched, _read_json(Path("data/editorial_overrides.json"), {})
    related_output, issue_output, explanations = {}, {}, []
    audit = [f"# Issue {issue} discovery audit", "", "Deterministic relevance scoring v1. Scores and override details are internal QA data only.", ""]
    for current in enriched:
        selected, scored = related_signals(current, archive, overrides=overrides)
        same_issue = more_from_issue(current, enriched)
        related_output[current["card_id"]], issue_output[current["card_id"]] = selected, same_issue
        explanations.extend(scored)
        selected_text = ", ".join(f"{x['card_id']} ({x['score']})" for x in selected) or "none"
        audit += [f"## {current['card_id']}", "", f"- Current card: {current['headline']}", f"- Related signals: {selected_text}", f"- More from Issue: {', '.join(x['card_id'] for x in same_issue) or 'none'}"]
        chosen_ids = {x["card_id"] for x in selected}
        for detail in scored:
            if detail["candidate_card"] in chosen_ids:
                audit.append(f"- {detail['candidate_card']} score reasons: {'; '.join(detail['reasons']) or 'no shared scoring factors'}")
        tied = len({x["score"] for x in scored}) < len(scored)
        audit.append(f"- Tie-breakers: {'published_at, same lane, then editorial override evaluated for equal scores' if tied else 'not needed'}")
        card_warnings = [w for w in warnings if w.startswith(current["card_id"] + ":")]
        audit += [f"- Metadata warnings: {'; '.join(card_warnings) if card_warnings else 'none'}", ""]
        _augment_article(issue_dir / "articles" / f"{current['card_id']}.html", selected, same_issue, issue)
    discovery_dir = issue_dir / "discovery"
    _write_json(discovery_dir / "related_signals.json", related_output)
    _write_json(discovery_dir / "more_from_issue.json", issue_output)
    _write_json(discovery_dir / "relevance_score_explanations.json", explanations)
    (discovery_dir / "discovery_audit.md").write_text("\n".join(audit) + "\n", encoding="utf-8")
