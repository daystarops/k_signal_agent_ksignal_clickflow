from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from PIL import Image

from ksignal.utils.files import ensure_dir, slugify

REJECT = re.compile(r"(?:logo|avatar|profile|icon|emoji|banner|advert|sprite|badge)", re.I)
VIDEO_HOSTS = ("youtube.com", "youtu.be", "twitter.com", "x.com", "instagram.com")


def _candidate(url: str, page_url: str, title: str = "", width: int = 0, height: int = 0, kind: str = "image", origin: str = "article") -> dict:
    absolute = urljoin(page_url, url)
    domain = urlparse(absolute).netloc.lower()
    size_score = 0.15 if width >= 800 or height >= 600 else 0.08 if width >= 400 or height >= 300 else 0
    origin_score = {"article": .72, "og": .78, "twitter": .74, "video": .76}.get(origin, .55)
    penalty = .5 if REJECT.search(f"{absolute} {title}") else 0
    score = max(0, min(.98, origin_score + size_score - penalty))
    return {"media_url": absolute, "page_url": page_url, "title": title, "source_domain": domain, "width": width or None, "height": height or None, "type": kind, "relevance_score": round(score, 2), "reason": f"{origin} media from the rendered source page"}


def collect_media_from_page(page, page_url: str) -> list[dict]:
    """Collect media from the current Playwright page; never starts another scrape."""
    rows = page.evaluate("""() => {
      const rows=[];
      for (const [selector, origin] of [['meta[property="og:image"]','og'],['meta[name="twitter:image"]','twitter']]) {
        document.querySelectorAll(selector).forEach(x => rows.push({url:x.content,title:'',width:0,height:0,type:'image',origin}));
      }
      document.querySelectorAll('article img, main img, [role="main"] img, .content img, .article img').forEach(x => rows.push({url:x.currentSrc||x.src,title:x.alt||x.title||'',width:x.naturalWidth||x.width,height:x.naturalHeight||x.height,type:'image',origin:'article'}));
      document.querySelectorAll('article iframe, main iframe, video, source').forEach(x => rows.push({url:x.src||x.currentSrc,title:x.title||'',width:x.width||0,height:x.height||0,type:'video',origin:'video'}));
      return rows;
    }""")
    return dedupe([_candidate(r["url"], page_url, r.get("title", ""), int(r.get("width") or 0), int(r.get("height") or 0), r.get("type", "image"), r.get("origin", "article")) for r in rows if r.get("url")])


def collect_media_from_saved_html(html_path: str | Path, page_url: str) -> list[dict]:
    """Use the DOM already saved by inspect-url; does not revisit the source."""
    path = Path(html_path)
    if not path.exists():
        return []
    soup = BeautifulSoup(path.read_text(encoding="utf-8", errors="ignore"), "html.parser")
    rows = []
    for selector, origin, attr in (("meta[property='og:image']", "og", "content"), ("meta[name='twitter:image']", "twitter", "content")):
        for node in soup.select(selector):
            if node.get(attr): rows.append(_candidate(node[attr], page_url, origin=origin))
    for img in soup.select("article img, main img, [role=main] img, .content img, .article img"):
        src = img.get("src") or img.get("data-src") or img.get("data-original")
        if src:
            rows.append(_candidate(src, page_url, img.get("alt", ""), int(img.get("width") or 0), int(img.get("height") or 0), "image", "article"))
    for node in soup.select("article iframe, main iframe, video, source"):
        src = node.get("src")
        if src and any(host in src for host in VIDEO_HOSTS): rows.append(_candidate(src, page_url, node.get("title", ""), kind="video", origin="video"))
    return dedupe(rows)


def dedupe(rows: list[dict]) -> list[dict]:
    found = {}
    for row in rows:
        url = row["media_url"]
        if url.startswith(("data:", "blob:")) or REJECT.search(f"{url} {row.get('title','')}"):
            continue
        if url not in found or row["relevance_score"] > found[url]["relevance_score"]:
            found[url] = row
    return sorted(found.values(), key=lambda row: row["relevance_score"], reverse=True)


def _crop_receipt(source: Path, destination: Path) -> None:
    with Image.open(source) as image:
        image = image.convert("RGB")
        width, height = image.size
        top = min(int(height * .08), 240)
        usable = image.crop((0, top, width, height))
        target_ratio = 16 / 9
        crop_height = min(usable.height, int(usable.width / target_ratio))
        y = max(0, min(int(usable.height * .08), usable.height - crop_height))
        usable.crop((0, y, usable.width, y + crop_height)).resize((1200, 675)).save(destination, quality=90)


def enrich_issue(issue: str, output_root: str | Path = "outputs/issues", inspect_dir: str | Path = "outputs/inspect") -> tuple[Path, list[str]]:
    from core.web_searcher import search_media
    issue_dir = Path(output_root) / issue
    cards_path = issue_dir / "editorial_cards.json"
    if not cards_path.exists():
        raise FileNotFoundError(f"Build Issue {issue} before enriching media.")
    cards = json.loads(cards_path.read_text(encoding="utf-8"))
    media_dir = ensure_dir(issue_dir / "media")
    signal_by_url = {}
    for path in Path(inspect_dir).glob("*.signal_card.json"):
        try:
            row = json.loads(path.read_text(encoding="utf-8")); signal_by_url[row.get("url", "")] = row
        except ValueError:
            pass
    manifest, notices = {}, []
    browser = context = page = None
    try:
        from playwright.sync_api import sync_playwright
        manager = sync_playwright().start()
        browser = manager.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 900})
        page = context.new_page()
        for index, card in enumerate(cards, 1):
            signal = signal_by_url.get(card["url"], {})
            prefix = slugify(card["url"])
            saved_html = Path(inspect_dir) / "screenshots" / f"{prefix}.html"
            candidates = collect_media_from_saved_html(saved_html, card["url"])
            usable = next((c for c in candidates if c["type"] == "image" and c["relevance_score"] >= .70), None)
            video = next((c for c in candidates if c["type"] == "video" and c["relevance_score"] >= .70), None)
            fallback_used = False
            if not usable and not video:
                fallback_used = True
                query_parts = [card["title"], card["korean_quote"], card["source"], card["lane"], *card.get("watch_next", [])]
                searched = search_media(page, " ".join(query_parts), video_relevant=bool(re.search(r"song|video|music|performance|Billlie|Work", card["title"], re.I)))
                usable = next((c for c in searched if c["type"] in ("image", "thumbnail") and c["relevance_score"] >= .70), None)
                video = next((c for c in searched if c["type"] == "video" and c["relevance_score"] >= .70), video)
            source_screenshot = next((Path(p) for p in signal.get("screenshot_paths", []) if Path(p).exists()), None)
            saved_screenshot = ""
            if source_screenshot:
                screenshot_copy = media_dir / f"card_{index:02d}_source{source_screenshot.suffix or '.png'}"
                shutil.copy2(source_screenshot, screenshot_copy)
                saved_screenshot = str(screenshot_copy)
            hero_path, hero_url, credit, media_type, confidence, reason = "", "", "", "fallback", "medium", "source screenshot fallback"
            if usable:
                try:
                    response = context.request.get(usable["media_url"], timeout=20000)
                    if response.ok and len(response.body()) > 10000:
                        content_type = response.headers.get("content-type", "")
                        ext = ".png" if "png" in content_type else ".webp" if "webp" in content_type else ".jpg"
                        target = media_dir / f"card_{index:02d}_hero{ext}"
                        target.write_bytes(response.body())
                        with Image.open(target) as check:
                            if check.width < 400 or check.height < 250: raise ValueError("image too small")
                        hero_path, hero_url, credit, media_type, confidence, reason = str(target), usable["media_url"], usable["source_domain"], "image", "high", usable["reason"]
                except Exception as exc:
                    notices.append(f"Card {index}: candidate download rejected ({exc})")
            if not hero_path:
                screenshot = source_screenshot
                if screenshot:
                    target = media_dir / f"card_{index:02d}_receipt.jpg"
                    _crop_receipt(screenshot, target)
                    hero_path, hero_url, credit, media_type = str(target), card["url"], card["source"], "screenshot"
                else:
                    notices.append(f"Card {index}: no source screenshot available")
            rights_status = "source_screenshot" if media_type == "screenshot" else "unknown" if fallback_used else "source_embedded"
            manifest[str(index)] = {"hero_image_path": hero_path, "hero_source_url": hero_url, "hero_credit": credit, "video_url": video["media_url"] if video else "", "video_thumbnail_path": hero_path if video else "", "media_confidence": confidence, "media_reason": reason, "source_screenshot_path": saved_screenshot, "rights_status": rights_status}
    finally:
        if browser: browser.close()
        if 'manager' in locals(): manager.stop()
    manifest_path = media_dir / "media_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest_path, notices
