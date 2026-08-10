from __future__ import annotations

import json
from pathlib import Path

from ksignal import issue_builder as builder


def export_social(issue: str, output_root: str | Path = "outputs/issues"):
    """Render every social card within one explicitly owned browser lifecycle."""
    issue_dir = Path(output_root) / issue
    data_path = issue_dir / "editorial_cards.json"
    if not data_path.exists():
        raise FileNotFoundError(f"Build Issue {issue} before exporting social cards.")
    cards = [builder.EditorialCard.model_validate(row) for row in json.loads(data_path.read_text(encoding="utf-8"))]
    social_dir = builder.ensure_dir(issue_dir / "social")
    html_paths: list[Path] = []
    for index, card in enumerate(cards, 1):
        html = ('<!doctype html><html><head><meta charset="utf-8"><style>'
                f'{builder.CSS}</style></head><body class="social-export"><main class="ig-shell">'
                f'{builder._social_markup(card)}</main></body></html>')
        path = social_dir / f"card_{index:02d}.html"
        path.write_text(html, encoding="utf-8")
        html_paths.append(path)

    png_paths: list[Path] = []
    errors: list[str] = []
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                context = browser.new_context(viewport={"width": 1080, "height": 1350})
                try:
                    page = context.new_page()
                    page.set_default_navigation_timeout(30_000)
                    for index, path in enumerate(html_paths, 1):
                        png = social_dir / f"card_{index:02d}.png"
                        try:
                            if page.is_closed():
                                page = context.new_page()
                                page.set_default_navigation_timeout(30_000)
                            page.goto(path.resolve().as_uri(), wait_until="load", timeout=30_000)
                            page.screenshot(path=str(png), full_page=False)
                            png_paths.append(png)
                        except Exception as exc:
                            errors.append(f"card_{index:02d}: {type(exc).__name__}: {exc}")
                            if not page.is_closed():
                                page.close()
                            page = context.new_page()
                            page.set_default_navigation_timeout(30_000)
                finally:
                    context.close()
            finally:
                browser.close()
    except Exception as exc:
        errors.append(f"Playwright setup: {type(exc).__name__}: {exc}")
    warning = "PNG export incomplete: " + " | ".join(errors) if errors else None
    return html_paths, png_paths, warning
