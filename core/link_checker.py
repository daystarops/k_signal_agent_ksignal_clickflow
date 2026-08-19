from __future__ import annotations

import json
import mimetypes
import os
import re
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from urllib.parse import quote_plus, unquote, urlparse

import httpx
from PIL import Image
from bs4 import BeautifulSoup

REGION = "local_us_machine"
DEAD_STRONG = (
    "대상을 찾을 수 없습니다", "권한이 없습니다", "비공개", "성인인증", "실명 확인",
    "이메일 인증", "삭제된 게시물", "존재하지 않는 게시물", "not found", "unavailable",
    "private", "forbidden", "access denied", "this content is not available",
)
LOGIN_TERMS = ("로그인", "회원가입", "login", "sign up")
BLOCK_TERMS = ("captcha", "verify you are human", "checking your browser", "cloudflare")
RAW_MEDIA_HOST = re.compile(r"(?:img|image|cdn|static|media)[.-]", re.I)


class BrowserFallback:
    def __init__(self):
        self.manager = self.browser = self.page = None

    def check(self, url: str) -> tuple[int | str, str, str, bool, str]:
        try:
            if not self.page:
                from playwright.sync_api import sync_playwright
                self.manager = sync_playwright().start()
                self.browser = self.manager.chromium.launch(headless=True)
                self.page = self.browser.new_page(viewport={"width": 1280, "height": 900})
            response = self.page.goto(url, wait_until="domcontentloaded", timeout=30000)
            self.page.wait_for_timeout(700)
            text = self.page.locator("body").inner_text(timeout=5000)[:50000]
            status = response.status if response else ""
            final_url = self.page.url
            gated, reason = _gated_reason(text, status)
            return status, final_url, text, gated, reason
        except Exception as exc:
            return "", url, "", False, f"Playwright navigation failed: {exc}"

    def close(self) -> None:
        if self.browser:
            self.browser.close()
        if self.manager:
            self.manager.stop()


def _gated_reason(text: str, status: int | str) -> tuple[bool, str]:
    lower = re.sub(r"\s+", " ", text).lower()
    for term in DEAD_STRONG:
        if term.lower() in lower:
            return True, f"dead/gated indicator: {term}"
    login_hits = sum(term.lower() in lower for term in LOGIN_TERMS)
    if login_hits >= 2 and len(lower) < 25000:
        return True, "page appears to be a login or signup wall"
    if any(term in lower for term in BLOCK_TERMS):
        return True, "automated access appears blocked"
    if str(status) in ("401", "403", "404", "410", "451"):
        return True, f"HTTP {status}"
    return False, ""


def _result(card_id: str, label: str, url: str, method: str, status: int | str, final_url: str, ok: bool, gated: bool, reason: str, asset_role: str = "") -> dict:
    return {"card_id": card_id, "label": label, "url": url, "method_used": method, "status_code": str(status), "final_url": final_url, "ok": bool(ok), "blocked_or_gated": bool(gated), "reason": reason, "checked_at": datetime.now(timezone.utc).isoformat(), "region_assumption": REGION, "needs_repair": not ok or gated, "asset_role": asset_role}


def check_local_media(card_id: str, label: str, value: str, asset_role: str = "") -> dict:
    path = Path(value)
    if not path.exists() or not path.is_file():
        return _result(card_id, label, value, "GET", "", value, False, False, "local media file is missing", asset_role)
    try:
        with Image.open(path) as image:
            image.verify()
        content_type = mimetypes.guess_type(path.name)[0] or ""
        ok = content_type.startswith("image/")
        return _result(card_id, label, value, "GET", 200, str(path.resolve()), ok, False, f"local image verified ({content_type})", asset_role)
    except Exception as exc:
        return _result(card_id, label, value, "GET", "", value, False, False, f"invalid local image: {exc}", asset_role)


def _persisted_article(issue_dir: Path, card: dict, newsletter_html: str) -> tuple[Path, str]:
    """Resolve the public article recorded by the completed issue output."""
    for path_value, route_value in (
        (card.get("article_path", ""), card.get("article_url", "")),
        (issue_dir / card.get("article_url", ""), card.get("article_url", "")),
    ):
        path = Path(path_value) if path_value else Path()
        if path_value and path.is_file() and route_value:
            return path, str(route_value).replace("\\", "/")

    soup = BeautifulSoup(newsletter_html, "html.parser")
    title = card.get("title", "").strip()
    for preview in soup.select("article.story-preview"):
        headline = preview.select_one("h2 a[href]")
        if not headline or headline.get_text(" ", strip=True) != title:
            continue
        route = str(headline.get("href", ""))
        path = issue_dir / unquote(urlparse(route).path)
        if route and path.is_file():
            return path, route
    return Path(card.get("article_path", "")), str(card.get("article_url", ""))


def _homepage_lead_error(soup: BeautifulSoup, valid_routes: set[str]) -> str | None:
    lead = soup.select_one("article.story-preview.lead h2 a[href]")
    if not lead:
        return "homepage lead article is missing"
    if lead.get("href") not in valid_routes:
        return "homepage lead does not point to a persisted article from the current issue"
    return None


def check_local_page(card_id: str, value: str, newsletter_html: str, route: str = "") -> dict:
    path = Path(value)
    exists = path.exists() and path.is_file()
    relative = route or f"articles/{path.name}"
    soup = BeautifulSoup(newsletter_html, "html.parser")
    preview = next(
        (node for node in soup.select("article.story-preview") if (node.select_one("h2 a") or {}).get("href") == relative),
        None,
    )
    primary = [] if preview is None else [
        node.get("href", "") for selector in ("a.hero", "h2 a", "a.read-signal")
        if (node := preview.select_one(selector)) is not None
    ]
    required = [] if preview is None else [preview.select_one("h2 a"), preview.select_one("a.read-signal")]
    ok = exists and preview is not None and all(required) and bool(primary) and all(href == relative for href in primary)
    reason = (
        "internal article exists and newsletter hero/headline/CTA point to it"
        if ok else f"article exists={exists}; persisted route={relative!r}; newsletter primary links={primary}"
    )
    return _result(card_id, "article", relative, "GET", 200 if exists else "", str(path.resolve()) if exists else value, ok, False, reason, "internal article")


def _human_video_url(url: str) -> str:
    youtube = re.search(r"youtube(?:-nocookie)?\.com/embed/([^?&/]+)", url or "")
    if youtube:
        return f"https://www.youtube.com/watch?v={youtube.group(1)}"
    tweet = re.search(r"(?:[?&]id=|/status/)(\d+)", url or "")
    if "twitter.com/embed" in (url or "") and tweet:
        return f"https://x.com/i/status/{tweet.group(1)}"
    return url or ""

def check_remote(card_id: str, label: str, url: str, browser: BrowserFallback, expect_image: bool = False, asset_role: str = "") -> dict:
    if not url:
        return _result(card_id, label, url, "HEAD", "", url, False, False, "URL is missing", asset_role)
    method, status, final_url, body, content_type, reason = "HEAD", "", url, "", "", ""
    try:
        with httpx.Client(follow_redirects=True, timeout=12, headers={"User-Agent": "Mozilla/5.0 K-Signal-LinkChecker/1.0"}) as client:
            head = client.head(url)
            status, final_url, content_type = head.status_code, str(head.url), head.headers.get("content-type", "")
            need_get = status in (403, 405) or status >= 400 or not expect_image or (expect_image and not content_type.lower().startswith("image/"))
            if need_get:
                method = "GET"
                response = client.get(url)
                status, final_url, content_type = response.status_code, str(response.url), response.headers.get("content-type", "")
                body = response.text[:50000] if "text" in content_type or "html" in content_type or not content_type else ""
    except Exception as exc:
        reason = f"HTTP request failed: {exc}"
    gated, gated_reason = _gated_reason(body, status)
    status_ok = isinstance(status, int) and 200 <= status < 400
    type_ok = not expect_image or content_type.lower().startswith("image/")
    blocked = gated or not status_ok or not type_ok
    if blocked:
        p_status, p_final, p_text, p_gated, p_reason = browser.check(url)
        method = "PLAYWRIGHT"
        if p_status != "": status = p_status
        final_url = p_final
        gated = p_gated
        status_ok = isinstance(status, int) and 200 <= status < 400
        if expect_image:
            # Browser navigation proves reachability; HTTP content-type still proves image identity.
            type_ok = content_type.lower().startswith("image/")
        blocked = gated or not status_ok or not type_ok
        reason = p_reason or gated_reason or reason
    else:
        reason = "image reachable" if expect_image else "page reachable"
    if expect_image and status_ok and not type_ok:
        reason = f"expected image/* but received {content_type or 'unknown content type'}"
    return _result(card_id, label, url, method, status, final_url, status_ok and type_ok and not gated, gated, reason or gated_reason, asset_role)


def _render_audit(audit: dict, out_path: Path) -> None:
    rows = []
    for result in audit["links"]:
        state = "pass" if result["ok"] and not result["blocked_or_gated"] else "fail"
        rows.append(f'<tr class="{state}"><td>{escape(result["card_id"])}</td><td>{escape(result["label"])}</td><td><a href="{escape(result["url"])}" target="_blank" rel="noopener noreferrer">{escape(result["asset_role"] or result["label"])}</a></td><td>{escape(result["method_used"])}</td><td>{escape(result["status_code"])}</td><td>{"PASS" if state == "pass" else "FAIL"}</td><td>{escape(result["reason"])}</td></tr>')
    cards = []
    for card in audit["cards"]:
        state = "pass" if card["publishable"] and not card["warning"] else "warn" if card["publishable"] else "fail"
        cards.append(f'<div class="summary {state}"><b>Card {escape(card["card_id"])} · {state.upper()}</b><span>{escape(card["reason"])}</span></div>')
    html = f'''<!doctype html><html><head><meta charset="utf-8"><title>K-Signal Link Audit</title><style>body{{font:14px Arial;margin:32px;color:#101828}}h1{{font-size:32px}}.overall{{padding:18px;background:{'#d1fadf' if audit['publishable'] else '#fee4e2'};font-weight:800}}.summary{{display:flex;justify-content:space-between;padding:12px;margin:8px 0;border-left:6px solid}}.pass{{border-color:#079455;background:#ecfdf3}}.warn{{border-color:#dc6803;background:#fffaeb}}.fail{{border-color:#d92d20;background:#fef3f2}}table{{border-collapse:collapse;width:100%;margin-top:24px}}th,td{{padding:9px;border:1px solid #ddd;text-align:left}}a{{color:#b42318}}code{{background:#eee;padding:2px 4px}}</style></head><body><h1>K-Signal Issue {escape(audit['issue'])} · Publish Audit</h1><p class="overall">{'PUBLISHABLE' if audit['publishable'] else 'NOT PUBLISHABLE'} · checked from {REGION}</p>{''.join(cards)}<table><thead><tr><th>Card</th><th>Label</th><th>Link</th><th>Method</th><th>Status</th><th>Result</th><th>Reason</th></tr></thead><tbody>{''.join(rows)}</tbody></table><h2>Future regional redirects</h2><p><code>/go/{escape(audit['issue'])}/{{card_id}}/source</code> and <code>/go/{escape(audit['issue'])}/{{card_id}}/backup</code> can later be implemented with Cloudflare Workers using <code>cf-ipcountry</code>, Vercel Edge Middleware, or a FastAPI redirect endpoint with optional regional cloud checks. Static HTML performs no IP detection.</p></body></html>'''
    out_path.write_text(html, encoding="utf-8")


def check_issue_links(issue: str, output_root: str | Path = "outputs/issues") -> tuple[Path, Path, dict]:
    issue_dir = Path(output_root) / issue
    cards = json.loads((issue_dir / "editorial_cards.json").read_text(encoding="utf-8"))
    manifest_path = issue_dir / "media" / "media_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    newsletter_path = issue_dir / "newsletter.html"
    newsletter_html = newsletter_path.read_text(encoding="utf-8") if newsletter_path.exists() else ""
    links, summaries, browser = [], [], BrowserFallback()
    try:
        for index, card in enumerate(cards, 1):
            card_id = f"{index:02d}"
            media = manifest.get(str(index), {})
            source_url = card.get("source_url") or card.get("url", "")
            article_path, article_url = _persisted_article(issue_dir, card, newsletter_html)
            embed_url = card.get("video_embed_url") or (card.get("video_url", "") if "/embed/" in card.get("video_url", "") or "platform.twitter.com/embed/" in card.get("video_url", "") else "")
            hero_check = (
                check_local_media(card_id, "hero", card.get("hero_image_path", ""), "local hero")
                if card.get("hero_image_path")
                else _result(
                    card_id, "hero", embed_url, "EMBED", 200, embed_url, True, False,
                    "primary media is a provider embed", "embedded video primary",
                )
                if embed_url
                else check_local_media(card_id, "hero", "", "local hero")
            )
            checks = [
                check_remote(card_id, "source", source_url, browser, asset_role="original source"),
                check_remote(card_id, "backup", card.get("backup_url", ""), browser, asset_role="backup"),
                hero_check,
                check_local_page(card_id, str(article_path), newsletter_html, article_url),
            ]
            if card.get("hero_image_source_url"):
                checks.append(check_remote(card_id, "hero", card["hero_image_source_url"], browser, expect_image=True, asset_role="hero source URL"))
            click_url = card.get("video_click_url") or _human_video_url(embed_url)
            if embed_url:
                checks.append(check_remote(card_id, "video", embed_url, browser, asset_role="video iframe"))
            if click_url:
                checks.append(check_remote(card_id, "video", click_url, browser, asset_role="video click"))
            if card.get("video_thumbnail_path"):
                checks.append(check_local_media(card_id, "video", card["video_thumbnail_path"], "video thumbnail"))
            media_source = media.get("hero_source_url", "")
            if media_source and media_source != card.get("hero_image_source_url"):
                checks.append(check_remote(card_id, "hero", media_source, browser, expect_image=True, asset_role="manifest media source"))
            links.extend(checks)
            source, backup, hero, article = checks[:4]
            embed_checks = [row for row in checks if row["asset_role"] == "video iframe"]
            click_checks = [row for row in checks if row["asset_role"] == "video click"]
            link_ok = source["ok"] or backup["ok"]
            video_ok = not embed_url or any(row["ok"] for row in embed_checks) or any(row["ok"] for row in click_checks)
            publishable = link_ok and hero["ok"] and article["ok"] and video_ok
            warning = publishable and not source["ok"] and backup["ok"]
            reason = "source failed; tested backup works" if warning else "internal article, receipts, and media checks passed" if publishable else "internal article, source/backup, hero, or video requirement failed"
            summaries.append({"card_id": card_id, "source_status": "pass" if source["ok"] else "gated" if source["blocked_or_gated"] else "fail", "backup_status": "pass" if backup["ok"] else "gated" if backup["blocked_or_gated"] else "fail", "article_status": "pass" if article["ok"] else "fail", "publishable": publishable, "warning": warning, "reason": reason})
    finally:
        browser.close()
    audit = {"issue": issue, "checked_at": datetime.now(timezone.utc).isoformat(), "region_assumption": REGION, "publishable": all(row["publishable"] for row in summaries), "cards": summaries, "links": links}
    json_path, html_path = issue_dir / "link_audit.json", issue_dir / "link_audit.html"
    json_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    _render_audit(audit, html_path)
    return json_path, html_path, audit

def _search_backup(card: dict, engine: str = "naver") -> tuple[str, str, str]:
    query = " ".join([card.get("title", ""), card.get("korean_quote", "")[:80], *card.get("watch_next", [])])
    encoded = quote_plus(query)
    if engine == "naver":
        return f"https://search.naver.com/search.naver?where=nexearch&query={encoded}", "Backup Search", "Naver search built from the Korean receipt and entities"
    if engine == "google":
        domain = urlparse(card.get("url", "")).netloc
        return f"https://www.google.com/search?q={quote_plus(query + ' site:' + domain)}", "Backup Search", "Google source-domain recovery search"
    return f"https://www.bing.com/search?q={encoded}", "Backup Search", "Bing recovery search"


def repair_issue_links(issue: str, output_root: str | Path = "outputs/issues") -> tuple[Path, Path, dict]:
    issue_dir = Path(output_root) / issue
    audit_path = issue_dir / "link_audit.json"
    if not audit_path.exists():
        check_issue_links(issue, output_root)
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    cards_path = issue_dir / "editorial_cards.json"
    cards = json.loads(cards_path.read_text(encoding="utf-8"))
    summaries = {row["card_id"]: row for row in audit["cards"]}
    for index, card in enumerate(cards, 1):
        status = summaries.get(f"{index:02d}", {})
        backup_host = urlparse(card.get("backup_url", "")).netloc
        raw_only = bool(RAW_MEDIA_HOST.search(backup_host)) or re.search(r"\.(?:jpg|jpeg|png|webp)(?:\?|$)", card.get("backup_url", ""), re.I)
        source_failed = status.get("source_status") != "pass"
        backup_failed = status.get("backup_status") != "pass"
        is_card_one = index == 1 or "4059776426" in card.get("url", "")
        embed = card.get("video_embed_url") or card.get("video_url", "")
        click = card.get("video_click_url") or _human_video_url(embed)
        if is_card_one:
            embed = click = ""
            card["video_url"] = card["video_embed_url"] = card["video_click_url"] = card["video_thumbnail_path"] = ""
            card["media_type"] = "image"
        else:
            card["video_embed_url"], card["video_click_url"] = embed, click
        if source_failed or backup_failed or raw_only or is_card_one or not card.get("backup_url") or "/embed/" in card.get("backup_url", "") or "platform.twitter.com/embed/" in card.get("backup_url", ""):
            if click and not raw_only:
                backup, label, reason = click, "Backup Video", "relevant human-facing video page attached to the card"
            else:
                backup, label, reason = _search_backup(card, "naver")
            card["backup_url"], card["backup_label"], card["backup_reason"] = backup, label, reason
        card["source_url"] = card.get("source_url") or card.get("url", "")
        card["source_label"] = "Original Source · may require login" if status.get("source_status") == "gated" else "Original Source"
        card["source_status"] = status.get("source_status", "unknown")
        card["backup_status"] = status.get("backup_status", "unknown")
        card["publishable"] = False
    cards_path.write_text(json.dumps(cards, ensure_ascii=False, indent=2), encoding="utf-8")
    from ksignal.issue_builder import rebuild_issue
    rebuild_issue(issue, output_root)
    json_path, html_path, fresh = check_issue_links(issue, output_root)
    fresh_status = {row["card_id"]: row for row in fresh["cards"]}
    cards = json.loads(cards_path.read_text(encoding="utf-8"))
    for index, card in enumerate(cards, 1):
        status = fresh_status[f"{index:02d}"]
        card["source_status"] = status["source_status"]
        card["backup_status"] = status["backup_status"]
        card["publishable"] = status["publishable"]
    cards_path.write_text(json.dumps(cards, ensure_ascii=False, indent=2), encoding="utf-8")
    rebuild_issue(issue, output_root)
    return json_path, html_path, fresh

def publish_audit(issue: str, output_root: str | Path = "outputs/issues") -> tuple[bool, list[str], Path]:
    issue_dir = Path(output_root) / issue
    audit_path = issue_dir / "link_audit.json"
    errors = []
    if not audit_path.exists():
        return False, ["link_audit.json is missing"], issue_dir / "link_audit.html"
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    cards = json.loads((issue_dir / "editorial_cards.json").read_text(encoding="utf-8"))
    audited = {(row["card_id"], row["label"], row["url"]) for row in audit.get("links", [])}
    summaries = {row["card_id"]: row for row in audit.get("cards", [])}
    newsletter_path = issue_dir / "newsletter.html"
    html = newsletter_path.read_text(encoding="utf-8") if newsletter_path.exists() else ""
    soup = BeautifulSoup(html, "html.parser")
    visible = soup.get_text(" ")
    if "Four signals from this week." not in visible:
        errors.append("newsletter is missing the required weekly heading")
    if "What K-Signal tracks" in visible or "Native Korean readers:" in visible:
        errors.append("newsletter exposes removed homepage copy")
    if '<meta name="theme-color" content="#f4f5f6">' not in html or '<meta name="color-scheme" content="light">' not in html:
        errors.append("newsletter is missing locked light-mode color metadata")
    if "opacity:.03" not in html or "--bg-mobile:#f5f6f7" not in html:
        errors.append("mobile watermark or neutral background is missing")
    if not soup.select_one('header.site-header img[src="assets/ksignal-logo.png"]'):
        errors.append("homepage compact official logo is missing")
    if len(soup.select("nav.lane-nav .lane-item")) != 5:
        errors.append("homepage lane dropdown navigation is incomplete")
    persisted = [_persisted_article(issue_dir, card, html) for card in cards]
    valid_routes = {route for path, route in persisted if path.is_file() and route}
    if lead_error := _homepage_lead_error(soup, valid_routes):
        errors.append(lead_error)
    if soup.select("article.story-preview .translation, article.story-preview .internet-read, article.story-preview .receipts"):
        errors.append("homepage previews expose full article context")
    watermark_css = html.split(".watermark-page::before", 1)[1] if ".watermark-page::before" in html else ""
    if "transform:rotate" in watermark_css or "mix-blend-mode" in watermark_css or "backdrop-filter" in watermark_css:
        errors.append("watermark uses a transform or blending effect that can break mobile rendering")
    public_forbidden = (
        "Original source passed", "latest local check", "Naver search built", "Link audit:",
        "receipts, and media checks passed", "source_status", "backup_status",
        "media_confidence", "publishable", "debug", "audit passed", "Native Korean readers:",
    )
    for phrase in public_forbidden:
        if phrase.lower() in html.lower():
            errors.append(f"newsletter exposes operational text: {phrase}")
    logo_source = Path(os.getenv("LOGO_ASSET_PATH", "assets/brand/ksignal-logo.png"))
    logo_output = issue_dir / "assets" / "ksignal-logo.png"
    watermark_tiles = (
        (issue_dir / "assets" / "ksignal-watermark-tile.png", (420, 320), "desktop"),
        (issue_dir / "assets" / "ksignal-watermark-tile-mobile.png", (480, 360), "mobile"),
    )
    if logo_source.exists():
        if not logo_output.exists():
            errors.append("watermark logo output is missing")
        elif logo_source.read_bytes() != logo_output.read_bytes():
            errors.append("watermark output does not match the supplied logo asset")
        for tile_path, expected_size, label in watermark_tiles:
            if not tile_path.exists():
                errors.append(f"{label} pre-rotated watermark tile is missing")
                continue
            with Image.open(tile_path) as tile:
                alpha = tile.convert("RGBA").getchannel("A")
                bbox = alpha.getbbox()
                if tile.size != expected_size or not bbox:
                    errors.append(f"{label} watermark tile has invalid dimensions or content")
                elif bbox[0] <= 0 or bbox[1] <= 0 or bbox[2] >= tile.width or bbox[3] >= tile.height:
                    errors.append(f"{label} watermark tile lacks transparent padding")
        if "watermark-page" not in html or "ksignal-watermark-tile.png" not in html or "ksignal-watermark-tile-mobile.png" not in html:
            errors.append("newsletter pre-rotated watermark pattern is missing")
    else:
        errors.append(f"watermark requested but logo asset is missing: {logo_source}")
    newsletter_cards = soup.select("article.story-preview")
    if len(newsletter_cards) != len(cards):
        errors.append("newsletter card count does not match editorial cards")
    banned_hosts = ("youtube.com", "youtu.be", "x.com", "twitter.com", "theqoo.net", "fmkorea.com", "reddit.com")
    for index, card in enumerate(cards, 1):
        cid = f"{index:02d}"
        source_url = card.get("source_url") or card.get("url", "")
        if (cid, "source", source_url) not in audited or (cid, "backup", card.get("backup_url", "")) not in audited:
            errors.append(f"card {cid} source or backup has not been tested")
        article_path, expected = persisted[index - 1]
        if (cid, "article", expected) not in audited:
            errors.append(f"card {cid} internal article has not been tested")
        if not summaries.get(cid, {}).get("publishable"):
            errors.append(f"card {cid} failed link/media publishing rules")
        if not article_path.exists():
            errors.append(f"card {cid} internal article page is missing")
            continue
        node = next((item for item in newsletter_cards if (item.select_one("h2 a") or {}).get("href", "") == expected), None)
        if node:
            primary_links = [
                anchor.get("href", "") for selector in ("a.hero", "h2 a", "a.read-signal")
                if (anchor := node.select_one(selector)) is not None
            ]
            if not node.select_one("h2 a") or not node.select_one("a.read-signal") or any(href != expected for href in primary_links):
                errors.append(f"card {cid} newsletter hero/headline/CTA do not all use the internal article")
            if node.select(".receipt"):
                errors.append(f"card {cid} newsletter still contains prominent receipt controls")
            for anchor in node.select("a[href]"):
                href = anchor.get("href", "")
                host = urlparse(href).netloc.lower()
                if host or any(banned in href.lower() for banned in banned_hosts):
                    errors.append(f"card {cid} newsletter contains an external primary click: {href}")
        article_html = article_path.read_text(encoding="utf-8")
        for phrase in public_forbidden:
            if phrase.lower() in article_html.lower():
                errors.append(f"card {cid} article exposes operational text: {phrase}")
        if logo_source.exists() and ("watermark-page" not in article_html or "../assets/ksignal-watermark-tile.png" not in article_html or "../assets/ksignal-watermark-tile-mobile.png" not in article_html):
            errors.append(f"card {cid} article watermark pattern is missing")
        article = BeautifulSoup(article_html, "html.parser")
        comment_form = article.select_one('form[name="ksignal-comment"][data-netlify="true"]')
        comment_toggle = article.select_one('button.comment-toggle[aria-expanded="false"]')
        comment_panel = article.select_one('.comment-panel[hidden]')
        required_comment_fields = {"issue_id", "card_id", "article_slug", "source_page", "signal_id", "consent_state", "comment"}
        present_comment_fields = {field.get("name") for field in article.select('form[name="ksignal-comment"] [name]')}
        if not comment_form or not comment_toggle or not comment_panel or not required_comment_fields.issubset(present_comment_fields):
            errors.append(f"card {cid} comment capture is missing or not collapsed by default")
        pills = article.select("a.pill[href]")
        if len(pills) < 2:
            errors.append(f"card {cid} article is missing Source/Backup receipts")
        for anchor in article.select("a[href]"):
            href = anchor.get("href", "")
            if "/embed/" in href or "platform.twitter.com/embed/" in href or "/embed/Tweet.html" in href:
                errors.append(f"card {cid} user-facing href contains an embed URL")
            if urlparse(href).scheme in ("http", "https"):
                rel = set(anchor.get("rel", []))
                if anchor.get("target") != "_blank" or not {"noopener", "noreferrer"}.issubset(rel):
                    errors.append(f"card {cid} external article link lacks safe new-tab attributes")
        embed = card.get("video_embed_url", "")
        if embed and not any(frame.get("src") == embed for frame in article.select("iframe[src]")):
            errors.append(f"card {cid} video embed is missing from its article iframe")
        if card.get("video_click_url") and ("/embed/" in card["video_click_url"] or "platform.twitter.com/embed/" in card["video_click_url"]):
            errors.append(f"card {cid} video_click_url is not human-facing")
    for index in range(1, len(cards) + 1):
        social_path = issue_dir / "social" / f"card_{index:02d}.html"
        if social_path.exists():
            social_html = social_path.read_text(encoding="utf-8")
            for phrase in public_forbidden:
                if phrase.lower() in social_html.lower():
                    errors.append(f"card {index:02d} social output exposes operational text: {phrase}")
    static_ok = not errors
    static_error_count = len(errors)
    playwright_ok = False
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 390, "height": 844})
            page.goto(newsletter_path.resolve().as_uri(), wait_until="load")
            mobile = page.evaluate("""() => {
                const wm = getComputedStyle(document.body, "::before");
                const card = document.querySelector(".story-preview");
                const display = selector => {
                    const element = card.querySelector(selector);
                    return element ? getComputedStyle(element).display : null;
                };
                return {
                    overflow: document.documentElement.scrollWidth > window.innerWidth,
                    watermark_image: wm.backgroundImage,
                    watermark_transform: wm.transform,
                    watermark_opacity: Number(wm.opacity),
                    card_width: card.getBoundingClientRect().width,
                    visible: [display("h2"), display(".dek"), display(".read-signal")],
                };
            }""")
            browser.close()
        if mobile["overflow"]:
            errors.append("mobile newsletter has horizontal overflow")
        if not mobile["watermark_image"] or mobile["watermark_image"] == "none" or "ksignal-watermark-tile-mobile.png" not in mobile["watermark_image"]:
            errors.append("mobile watermark layer is absent")
        if mobile["watermark_transform"] != "none":
            errors.append("mobile watermark layer uses a transform")
        if not (0.028 <= mobile["watermark_opacity"] <= 0.04):
            errors.append("mobile watermark opacity is outside the visible/subtle range")
        if mobile["card_width"] >= 1000:
            errors.append("1080px social export dimensions leaked into mobile newsletter")
        if any(value == "none" for value in mobile["visible"]):
            errors.append("mobile newsletter is missing a required feed element")
        playwright_ok = len(errors) == static_error_count
    except Exception as exc:
        errors.append(f"mobile browser regression check failed: {exc}")
    qa_path = issue_dir / "browser_qa_report.md"
    qa_text = qa_path.read_text(encoding="utf-8") if qa_path.exists() else ""
    harness_ok = "Result: **39/39 passed**" in qa_text
    status_path = issue_dir / "publish_audit_status.md"
    status_path.write_text(
        "# K-Signal Publish Audit Status\n\n"
        f"- Static audit: **{'PASSED' if static_ok else 'FAILED'}**\n"
        f"- Playwright audit: **{'PASSED' if playwright_ok else 'FAILED'}**\n"
        f"- Browser Harness interactive QA: **{'PASSED' if harness_ok else 'NOT PASSED / NOT RUN'}**\n"
        "- Translation automation: **NOT AUTOMATED -- manual checklist only** (`docs/AUTOTRANSLATE_QA.md`)\n",
        encoding="utf-8",
    )
    return not errors, errors, issue_dir / "link_audit.html"
