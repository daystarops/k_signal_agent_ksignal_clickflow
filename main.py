from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from dotenv import load_dotenv
from rich.console import Console
from ksignal.pipeline import run_pipeline
from ksignal.collectors.browser import render_page
from ksignal.schema import RawItem
from ksignal.models.openai_client import analyze_layout_with_vision, create_signal_card
from ksignal.utils.files import ensure_dir, slugify
from ksignal.exporters.webhook import push_webhook
from ksignal.issue_builder import export_social, load_inspected_cards, rebuild_issue, render_issue
from ksignal.engine.cli import register_engine_commands
from core.media_collector import enrich_issue
from core.link_checker import check_issue_links, publish_audit, repair_issue_links
from core.host_packager import create_host_package
from core.distribution_pack import create_distribution_pack
from core.instagram_pack import create_instagram_pack
from core.creative_scout import scout_creatives, write_creative_sources
from core.instagram_reels import render_reels

console = Console()


def cmd_run(args):
    load_dotenv()
    cards = run_pipeline(
        config_path=args.config,
        limit_per_source=args.limit_per_source,
        max_cards=args.max_cards,
        cards_per_category=args.cards_per_category,
        download_images=args.download_images,
        follow_article=args.follow_article,
        render_screenshots=args.render_screenshots,
        vision=args.vision,
        max_images_per_item=args.max_images_per_item,
        output_dir=args.output_dir,
    )
    console.print(f"\n[green]Done.[/green] Wrote {len(cards)} cards to {args.output_dir}/brief.md and {args.output_dir}/newsletter.html")


def cmd_push_webhook(args):
    load_dotenv()
    result = push_webhook(webhook_url=args.webhook_url, output_dir=args.output_dir)
    console.print(f"[green]Pushed to webhook.[/green] Cards: {result['sent_card_count']} | Brief chars: {result['sent_brief_chars']} | HTTP: {result['status_code']}")


def cmd_inspect_url(args):
    load_dotenv()
    out = Path(args.output_dir)
    ensure_dir(out / "screenshots")
    ensure_dir(out / "vision")
    prefix = slugify(args.name or args.url)
    render = render_page(args.url, out / "screenshots", name_prefix=prefix, mobile=args.mobile, full_page=args.full_page)
    text = Path(render["visible_text_path"]).read_text(encoding="utf-8") if Path(render["visible_text_path"]).exists() else ""
    item = RawItem(
        id=prefix[:16],
        source=args.source,
        source_family="manual_inspect",
        title=render["page_title"],
        url=args.url,
        snippet=text[:1200],
        title_source_url=render["final_url"],
        snippet_source_url=render["final_url"],
        title_response_id=render["response_id"],
        snippet_response_id=render["response_id"],
        screenshot_paths=[render["screenshot_path"]],
        metadata={"browser_render": render},
    )
    layout = analyze_layout_with_vision(item, item.screenshot_paths, visible_text_excerpt=text[:4000]) if args.vision else None
    if layout:
        (out / "vision" / f"{prefix}.json").write_text(layout.model_dump_json(indent=2), encoding="utf-8")
    card = create_signal_card(item, vision=layout) if args.card else None
    if card:
        (out / f"{prefix}.signal_card.json").write_text(card.model_dump_json(indent=2), encoding="utf-8")
    console.print(f"[green]Screenshot:[/green] {render['screenshot_path']}")
    if layout:
        console.print(f"[green]Vision layout:[/green] {out / 'vision' / (prefix + '.json')}")
    if card:
        console.print(f"[green]Signal card:[/green] {out / (prefix + '.signal_card.json')}")


def cmd_build_from_inspect(args):
    cards, notices = load_inspected_cards(args.inspect_dir, args.include_low_confidence)
    for notice in notices:
        console.print(f"[yellow]{notice}[/yellow]")
    html_path, md_path = render_issue(cards, args.issue, args.output_root)
    console.print(f"[green]Built Issue {args.issue}[/green] from {len(cards)} inspected card(s).")
    console.print(f"[green]Newsletter:[/green] {html_path}")
    console.print(f"[green]Brief:[/green] {md_path}")

def cmd_enrich_media(args):
    manifest, notices = enrich_issue(args.issue, args.output_root, args.inspect_dir)
    for notice in notices:
        console.print(f"[yellow]{notice}[/yellow]")
    console.print(f"[green]Media manifest:[/green] {manifest}")


def cmd_rebuild_issue(args):
    load_dotenv()
    html_path, md_path = rebuild_issue(args.issue, args.output_root, args.allow_unknown_rights)
    console.print(f"[green]Rebuilt Issue {args.issue}[/green]")
    console.print(f"[green]Newsletter:[/green] {html_path}")
    console.print(f"[green]Brief:[/green] {md_path}")


def cmd_export_social(args):
    html_paths, png_paths, warning = export_social(args.issue, args.output_root)
    console.print(f"[green]Exported {len(html_paths)} social HTML card(s) and {len(png_paths)} PNG(s).[/green]")
    if warning:
        console.print(f"[yellow]{warning}[/yellow]")


def cmd_check_links(args):
    json_path, html_path, audit = check_issue_links(args.issue, args.output_root)
    state = "PUBLISHABLE" if audit["publishable"] else "NOT PUBLISHABLE"
    console.print(f"[bold]{state}[/bold] · {json_path} · {html_path}")


def cmd_repair_links(args):
    load_dotenv()
    json_path, html_path, audit = repair_issue_links(args.issue, args.output_root)
    state = "PUBLISHABLE" if audit["publishable"] else "NOT PUBLISHABLE"
    console.print(f"[bold]{state} after repair[/bold] · {json_path} · {html_path}")


def cmd_publish_audit(args):
    ok, errors, html_path = publish_audit(args.issue, args.output_root)
    if ok:
        console.print(f"[green bold]STATIC + PLAYWRIGHT PUBLISH AUDIT PASSED[/green bold] · {html_path}")
        console.print(f"Browser Harness and translation status: {html_path.parent / 'publish_audit_status.md'}")
        return
    console.print(f"[red bold]PUBLISH AUDIT FAILED[/red bold] · {html_path}")
    for error in errors:
        console.print(f"[red]- {error}[/red]")
    raise SystemExit(1)

def cmd_create_host_package(args):
    package_dir, zip_path, entry_count = create_host_package(args.issue, args.output_root)
    console.print(f"[green]Created Netlify host package for Issue {args.issue}.[/green]")
    console.print(f"[green]Directory:[/green] {package_dir}")
    console.print(f"[green]ZIP:[/green] {zip_path}")
    console.print(f"[green]Validated entries:[/green] {entry_count}")

def cmd_create_distribution_pack(args):
    load_dotenv()
    pack_dir, public_url, file_count = create_distribution_pack(args.issue, args.output_root)
    console.print(f"[green]Created distribution pack for Issue {args.issue}.[/green]")
    console.print(f"[green]Directory:[/green] {pack_dir}")
    console.print(f"[green]Public URL:[/green] {public_url}")
    console.print(f"[green]Validated files:[/green] {file_count}")

def cmd_create_instagram_pack(args):
    load_dotenv()
    mode = "safe_public" if args.safe_public else "creator_mode"
    pack_dir, public_url, file_count, made_mp4 = create_instagram_pack(args.issue, args.output_root, args.allow_unknown_rights, mode=mode)
    console.print(f"[green]Created Instagram content pack for Issue {args.issue}.[/green]")
    console.print(f"[green]Directory:[/green] {pack_dir}")
    console.print(f"[green]Public URL:[/green] {public_url}")
    console.print(f"[green]Validated files:[/green] {file_count}")
    if not made_mp4:
        console.print("[yellow]ffmpeg unavailable; generated four reel frames and a reel script per card.[/yellow]")

def cmd_scout_creatives(args):
    mode = "creator_mode" if args.creator_mode else "safe_public"
    manifest, issue_path, ig_path = scout_creatives(args.issue, args.output_root, args.allow_unknown_rights, mode=mode)
    write_creative_sources(manifest, ig_path.parent / "CREATIVE_SOURCES.md")
    console.print(f"[green]Creative scout complete.[/green] {len(manifest['candidates'])} candidates")
    console.print(f"[green]Manifest:[/green] {issue_path}")

def cmd_render_reels(args):
    results = render_reels(args.issue, args.output_root)
    good = sum(item["success"] for item in results)
    console.print(f"[green]Rendered {good}/{len(results)} reels.[/green]")
    if good != len(results):
        raise SystemExit(1)


def main():
    parser = argparse.ArgumentParser(description="Korea Signal Engine sourcing + visual-context agent")
    sub = parser.add_subparsers(required=True)

    run = sub.add_parser("run", help="Collect enabled sources and create newsletter-ready brief")
    run.add_argument("--config", default="configs/sources.yaml")
    run.add_argument("--limit-per-source", type=int, default=5)
    run.add_argument("--max-cards", type=int, default=8)
    run.add_argument("--cards-per-category", type=int, default=1)
    run.add_argument("--output-dir", default="outputs")
    run.add_argument("--download-images", default=True, type=lambda x: str(x).lower() != "false")
    run.add_argument("--follow-article", default=True, type=lambda x: str(x).lower() != "false")
    run.add_argument("--render-screenshots", default=True, type=lambda x: str(x).lower() != "false")
    run.add_argument("--vision", default=True, type=lambda x: str(x).lower() != "false")
    run.add_argument("--max-images-per-item", type=int, default=3)
    run.set_defaults(func=cmd_run)

    inspect = sub.add_parser("inspect-url", help="Render one URL, screenshot it, and optionally run vision/context analysis")
    inspect.add_argument("url")
    inspect.add_argument("--name", default="")
    inspect.add_argument("--source", default="Manual URL")
    inspect.add_argument("--output-dir", default="outputs/inspect")
    inspect.add_argument("--vision", default=True, type=lambda x: str(x).lower() != "false")
    inspect.add_argument("--card", default=True, type=lambda x: str(x).lower() != "false")
    inspect.add_argument("--mobile", default=True, type=lambda x: str(x).lower() != "false")
    inspect.add_argument("--full-page", default=True, type=lambda x: str(x).lower() != "false")
    inspect.set_defaults(func=cmd_inspect_url)

    build = sub.add_parser("build-from-inspect", help="Build a branded issue from inspected signal cards")
    build.add_argument("--issue", required=True, help="Issue identifier, for example 001")
    build.add_argument("--inspect-dir", default="outputs/inspect")
    build.add_argument("--output-root", default="outputs/issues")
    build.add_argument("--include-low-confidence", action="store_true")
    build.set_defaults(func=cmd_build_from_inspect)
    enrich = sub.add_parser("enrich-media", help="Add source/search media to an existing issue")
    enrich.add_argument("--issue", required=True)
    enrich.add_argument("--output-root", default="outputs/issues")
    enrich.add_argument("--inspect-dir", default="outputs/inspect")
    enrich.set_defaults(func=cmd_enrich_media)

    rebuild = sub.add_parser("rebuild-issue", help="Rebuild a media-enriched issue")
    rebuild.add_argument("--issue", required=True)
    rebuild.add_argument("--output-root", default="outputs/issues")
    rebuild.add_argument("--allow-unknown-rights", action="store_true")
    rebuild.set_defaults(func=cmd_rebuild_issue)
    social = sub.add_parser("export-social", help="Export Issue cards as 1080x1350 social HTML and PNG files")
    social.add_argument("--issue", required=True, help="Issue identifier, for example 001")
    social.add_argument("--output-root", default="outputs/issues")
    social.set_defaults(func=cmd_export_social)
    links = sub.add_parser("check-links", help="Check every Issue source, backup, media, and video link")
    links.add_argument("--issue", required=True)
    links.add_argument("--output-root", default="outputs/issues")
    links.set_defaults(func=cmd_check_links)

    repair = sub.add_parser("repair-links", help="Repair dead, gated, or raw-media-only backup links")
    repair.add_argument("--issue", required=True)
    repair.add_argument("--output-root", default="outputs/issues")
    repair.set_defaults(func=cmd_repair_links)

    audit = sub.add_parser("publish-audit", help="Enforce link and media publishing rules")
    audit.add_argument("--issue", required=True)
    audit.add_argument("--output-root", default="outputs/issues")
    audit.set_defaults(func=cmd_publish_audit)
    host = sub.add_parser("create-host-package", help="Create a validated Netlify-ready Issue package and ZIP")
    host.add_argument("--issue", required=True)
    host.add_argument("--output-root", default="outputs/issues")
    host.set_defaults(func=cmd_create_host_package)
    distribution = sub.add_parser("create-distribution-pack", help="Create traffic-distribution assets and outreach copy for an Issue")
    distribution.add_argument("--issue", required=True)
    distribution.add_argument("--output-root", default="outputs/issues")
    distribution.set_defaults(func=cmd_create_distribution_pack)
    instagram = sub.add_parser("create-instagram-pack", help="Create carousel, story-sequence, and reel assets for an Issue")
    instagram.add_argument("--issue", required=True)
    instagram.add_argument("--output-root", default="outputs/issues")
    instagram.add_argument("--allow-unknown-rights", action="store_true", help="Private review only; public export blocks unknown rights by default")
    instagram_mode = instagram.add_mutually_exclusive_group()
    instagram_mode.add_argument("--creator-mode", action="store_true", help="Stage an aggressive rights-aware local creative plan (default)")
    instagram_mode.add_argument("--safe-public", action="store_true", help="Restrict outputs to conservative public-safe assets")
    instagram.set_defaults(func=cmd_create_instagram_pack)
    scout = sub.add_parser("scout-creatives", help="Create a rights-aware creative manifest for an Issue")
    scout.add_argument("--issue", required=True)
    scout.add_argument("--output-root", default="outputs/issues")
    scout.add_argument("--allow-unknown-rights", action="store_true", help="Private review mode")
    scout.add_argument("--creator-mode", action="store_true", help="Stage useful official/reference candidates for local review")
    scout.set_defaults(func=cmd_scout_creatives)
    reels = sub.add_parser("render-reels", help="Render prepared Instagram reel frames to MP4")
    reels.add_argument("--issue", required=True)
    reels.add_argument("--output-root", default="outputs/issues")
    reels.add_argument("--creator-mode", action="store_true", help="Render rights-safe local/generated creator-mode reels")
    reels.set_defaults(func=cmd_render_reels)
    push = sub.add_parser("push-webhook", help="Push latest outputs/brief.md + cards to n8n or any webhook")
    push.add_argument("--output-dir", default="outputs")
    push.add_argument("--webhook-url", default="")
    push.set_defaults(func=cmd_push_webhook)

    register_engine_commands(sub)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
