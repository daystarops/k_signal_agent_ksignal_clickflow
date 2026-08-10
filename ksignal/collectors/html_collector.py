from __future__ import annotations

import hashlib
from urllib.parse import urljoin
from bs4 import BeautifulSoup
import httpx
from ksignal.schema import RawItem
from ksignal.utils.images import normalize_url


def _text(el) -> str:
    if not el:
        return ""
    return " ".join(el.get_text(" ", strip=True).split())


def _attr(el, name: str) -> str:
    if not el:
        return ""
    return el.get(name) or ""


def collect_html_list(source: dict, limit: int = 10, user_agent: str = "Mozilla/5.0") -> list[RawItem]:
    url = source["url"]
    selectors = source.get("selectors", {})
    headers = {"User-Agent": user_agent, "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.7"}
    with httpx.Client(follow_redirects=True, timeout=25.0, headers=headers) as client:
        r = client.get(url)
        r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    item_sel = selectors.get("item", "article, li, tr")
    title_sel = selectors.get("title", "a")
    link_sel = selectors.get("link", "a")
    snippet_sel = selectors.get("snippet", "")
    image_sel = selectors.get("image", "img")

    rows: list[RawItem] = []
    for node in soup.select(item_sel):
        title_el = node.select_one(title_sel)
        link_el = node.select_one(link_sel) or title_el
        href = _attr(link_el, "href")
        absolute_url = urljoin(url, href) if href else url
        title = _text(title_el)
        snippet = _text(node.select_one(snippet_sel)) if snippet_sel else _text(node)
        if not title and not snippet:
            continue
        if len(title) < 2 and len(snippet) < 8:
            continue
        image_urls = []
        for img in node.select(image_sel)[:5]:
            src = img.get("src") or img.get("data-src") or img.get("data-original")
            normalized = normalize_url(url, src)
            if normalized:
                image_urls.append(normalized)
        uid_src = f"{source.get('name')}|{absolute_url}|{title}"
        uid = hashlib.sha1(uid_src.encode("utf-8")).hexdigest()[:16]
        rows.append(RawItem(
            id=uid,
            source=source.get("name", "unknown"),
            source_family=source.get("source_family"),
            category=source.get("category", "uncategorized"),
            title=title[:300],
            url=absolute_url,
            snippet=snippet[:2000],
            language=source.get("language", "ko"),
            image_urls=list(dict.fromkeys(image_urls)),
            metadata={"list_url": url, "collector": "html_list"}
        ))
        if len(rows) >= limit:
            break
    return rows


def enrich_article_dom(item: RawItem, user_agent: str = "Mozilla/5.0", max_text_chars: int = 8000) -> tuple[str, list[str]]:
    headers = {"User-Agent": user_agent, "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.7"}
    try:
        with httpx.Client(follow_redirects=True, timeout=25.0, headers=headers) as client:
            r = client.get(item.url)
            r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        for tag in soup(["script", "style", "noscript", "svg"]):
            tag.decompose()
        body_text = "\n".join([line.strip() for line in soup.get_text("\n").splitlines() if line.strip()])
        img_urls = []
        for img in soup.select("img")[:20]:
            src = img.get("src") or img.get("data-src") or img.get("data-original")
            normalized = normalize_url(item.url, src)
            if normalized:
                img_urls.append(normalized)
        return body_text[:max_text_chars], list(dict.fromkeys(img_urls))
    except Exception as e:
        return f"[DOM enrichment failed: {e}]", []
