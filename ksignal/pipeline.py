from __future__ import annotations

import os
from collections import defaultdict
from pathlib import Path
import yaml
from rich.console import Console
from ksignal.collectors.html_collector import collect_html_list, enrich_article_dom
from ksignal.collectors.naver_api import collect_naver_search
from ksignal.collectors.browser import render_page
from ksignal.models.openai_client import analyze_layout_with_vision, create_signal_card
from ksignal.renderers.newsletter import render_markdown
try:
    from ksignal.renderers.html_newsletter import render_html
except Exception:  # pragma: no cover
    render_html = None
from ksignal.schema import RawItem, SignalCard
from ksignal.utils.files import ensure_dir, write_jsonl, append_jsonl, slugify
from ksignal.utils.images import download_image

console = Console()
DEFAULT_CATEGORIES = ["government", "idols", "sports", "local_phenomenon"]


def load_config(path: str = "configs/sources.yaml") -> dict:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}


def load_sources(path: str = "configs/sources.yaml") -> list[dict]:
    data = load_config(path)
    return [s for s in data.get("sources", []) if s.get("enabled", False)]


def collect_sources(config_path: str = "configs/sources.yaml", limit_per_source: int = 5) -> list[RawItem]:
    user_agent = os.getenv("USER_AGENT", "Mozilla/5.0")
    rows: list[RawItem] = []
    for source in load_sources(config_path):
        console.print(f"[bold]Collecting[/bold] {source.get('name')} ({source.get('type')}) [{source.get('category','uncategorized')}]")
        try:
            if source["type"] == "html_list":
                items = collect_html_list(source, limit=limit_per_source, user_agent=user_agent)
            elif source["type"].startswith("naver_"):
                items = collect_naver_search(source)
            else:
                items = []
            rows.extend(items)
            console.print(f"  -> {len(items)} items")
        except Exception as e:
            console.print(f"[red]Failed source {source.get('name')}: {e}[/red]")
    return rows


def choose_balanced_items(items: list[RawItem], categories: list[str] | None = None, cards_per_category: int = 1, max_cards: int = 8) -> list[RawItem]:
    categories = categories or DEFAULT_CATEGORIES
    grouped: dict[str, list[RawItem]] = defaultdict(list)
    for item in items:
        grouped[item.category or "uncategorized"].append(item)
    chosen: list[RawItem] = []
    seen = set()

    # First guarantee the newsletter has the four requested lanes when data exists.
    for cat in categories:
        for item in grouped.get(cat, [])[:cards_per_category]:
            if item.id not in seen:
                chosen.append(item); seen.add(item.id)

    # Then fill the remainder with recency/source order.
    for item in items:
        if len(chosen) >= max_cards:
            break
        if item.id not in seen:
            chosen.append(item); seen.add(item.id)
    return chosen[:max_cards]


def enrich_items(items: list[RawItem], download_images: bool = True, follow_article: bool = True, render_screenshots: bool = True, vision: bool = True, max_images_per_item: int = 3, output_dir: str = "outputs") -> list[SignalCard]:
    ensure_dir(output_dir)
    ensure_dir(Path(output_dir) / "images")
    ensure_dir(Path(output_dir) / "screenshots")
    ensure_dir(Path(output_dir) / "dom")
    ensure_dir(Path(output_dir) / "vision")
    ensure_dir(Path(output_dir) / "cards")

    cards: list[SignalCard] = []
    user_agent = os.getenv("USER_AGENT", "Mozilla/5.0")

    for idx, item in enumerate(items, 1):
        console.print(f"[cyan]Enriching[/cyan] {idx}/{len(items)} [{item.category}] {item.title[:80]}")
        visible_text_excerpt = item.snippet

        if follow_article and item.url:
            page_title, dom_text, more_imgs, page_url, page_response_id = enrich_article_dom(item, user_agent=user_agent)
            dom_path = Path(output_dir) / "dom" / f"{idx:03d}-{slugify(item.title or item.id)}.txt"
            dom_path.write_text(dom_text, encoding="utf-8")
            item.dom_text_path = str(dom_path)
            item.title = page_title
            item.snippet = dom_text
            item.title_source_url = page_url
            item.snippet_source_url = page_url
            item.title_response_id = page_response_id
            item.snippet_response_id = page_response_id
            visible_text_excerpt = dom_text[:4500]
            item.image_urls = list(dict.fromkeys(item.image_urls + more_imgs))

        if download_images:
            for img_url in item.image_urls[:max_images_per_item]:
                local = download_image(img_url, Path(output_dir) / "images", prefix=f"{idx:03d}-{item.source}-{item.title}")
                if local:
                    item.local_image_paths.append(local)

        if render_screenshots and item.url:
            try:
                r = render_page(item.url, Path(output_dir) / "screenshots", name_prefix=f"{idx:03d}-{item.source}-{item.title}", user_agent=user_agent, mobile=True, full_page=True)
                item.screenshot_paths.append(r["screenshot_path"])
                item.metadata["visible_image_candidates"] = r.get("visible_image_candidates", [])[:12]
                if Path(r["visible_text_path"]).exists():
                    visible_text_excerpt = Path(r["visible_text_path"]).read_text(encoding="utf-8")[:4500]
            except Exception as e:
                item.metadata["screenshot_error"] = str(e)
                console.print(f"  [yellow]screenshot failed: {e}[/yellow]")

        layout = None
        if vision and item.screenshot_paths:
            layout = analyze_layout_with_vision(item, item.screenshot_paths, visible_text_excerpt=visible_text_excerpt)
            vpath = Path(output_dir) / "vision" / f"{idx:03d}-{slugify(item.title or item.id)}.json"
            vpath.write_text(layout.model_dump_json(indent=2), encoding="utf-8")

        card = create_signal_card(item, vision=layout)
        cpath = Path(output_dir) / "cards" / f"{idx:03d}-{slugify(card.title_english or card.title_original or item.id)}.json"
        cpath.write_text(card.model_dump_json(indent=2), encoding="utf-8")
        append_jsonl(Path(output_dir) / "signal_cards.jsonl", card)
        append_jsonl(Path(output_dir) / "raw_items.jsonl", item)
        cards.append(card)

    render_markdown(cards, Path(output_dir) / "brief.md", title="K Signal")
    if render_html:
        render_html(cards, Path(output_dir) / "newsletter.html", title="K Signal")
    return cards


def run_pipeline(config_path: str = "configs/sources.yaml", limit_per_source: int = 5, max_cards: int = 8, cards_per_category: int = 1, **kwargs) -> list[SignalCard]:
    output_dir = kwargs.get("output_dir", "outputs")
    ensure_dir(output_dir)
    for fn in [Path(output_dir) / "raw_items.jsonl", Path(output_dir) / "signal_cards.jsonl"]:
        try:
            fn.unlink()
        except FileNotFoundError:
            pass
    cfg = load_config(config_path)
    categories = cfg.get("categories") or DEFAULT_CATEGORIES
    items = collect_sources(config_path, limit_per_source=limit_per_source)
    selected = choose_balanced_items(items, categories=categories, cards_per_category=cards_per_category, max_cards=max_cards)
    write_jsonl(Path(output_dir) / "collected_items_preview.jsonl", selected)
    return enrich_items(selected, **kwargs)
