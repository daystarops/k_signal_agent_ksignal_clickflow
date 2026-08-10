from __future__ import annotations

import os
from pathlib import Path
from playwright.sync_api import sync_playwright
from ksignal.utils.files import ensure_dir, slugify
from core.media_collector import collect_media_from_page


def render_page(url: str, out_dir: str | Path, name_prefix: str = "page", user_agent: str | None = None, headless: bool | None = None, mobile: bool = True, wait_ms: int = 2500, full_page: bool = True) -> dict:
    """Render page with Playwright and save screenshot + visible text.

    This is the core upgrade: it captures what a human sees, not just HTML soup.
    """
    ensure_dir(out_dir)
    headless = headless if headless is not None else os.getenv("HEADLESS", "true").lower() != "false"
    prefix = slugify(name_prefix)
    screenshot_path = Path(out_dir) / f"{prefix}.png"
    text_path = Path(out_dir) / f"{prefix}.visible.txt"
    html_path = Path(out_dir) / f"{prefix}.html"

    iphone = {
        "viewport": {"width": 390, "height": 844},
        "device_scale_factor": 2,
        "is_mobile": True,
        "has_touch": True,
    }

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context_kwargs = {"user_agent": user_agent or os.getenv("USER_AGENT") or "Mozilla/5.0"}
        if mobile:
            context_kwargs.update(iphone)
        page = browser.new_page(**context_kwargs)
        page.goto(url, wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(wait_ms)
        # scroll a little to trigger lazy images, then back to top
        page.mouse.wheel(0, 900)
        page.wait_for_timeout(800)
        page.mouse.wheel(0, -900)
        page.wait_for_timeout(400)
        page.screenshot(path=str(screenshot_path), full_page=full_page)
        visible_text = page.locator("body").inner_text(timeout=10000)
        html = page.content()
        text_path.write_text(visible_text, encoding="utf-8")
        html_path.write_text(html, encoding="utf-8")
        # visible img srcs with bounding boxes
        media_candidates = collect_media_from_page(page, url)
        images = page.evaluate("""
        () => Array.from(document.images).slice(0, 80).map(img => {
          const r = img.getBoundingClientRect();
          return {src: img.currentSrc || img.src, alt: img.alt || '', x: r.x, y: r.y, w: r.width, h: r.height, visible: r.width > 20 && r.height > 20};
        }).filter(x => x.src && x.visible)
        """)
        browser.close()
    return {
        "screenshot_path": str(screenshot_path),
        "visible_text_path": str(text_path),
        "html_path": str(html_path),
        "visible_image_candidates": images,
        "media_candidates": media_candidates,
    }
