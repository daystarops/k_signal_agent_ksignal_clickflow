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


def response_id(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


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
            title_source_url=str(r.url),
            snippet_source_url=str(r.url),
            title_response_id=response_id(r.text),
            snippet_response_id=response_id(r.text),
            language=source.get("language", "ko"),
            image_urls=list(dict.fromkeys(image_urls)),
            metadata={"list_url": url, "collector": "html_list"}
        ))
        if len(rows) >= limit:
            break
    return rows


def extract_page_text(html: str, page_url: str, max_text_chars: int = 8000) -> tuple[str, str, list[str]]:
    """Extract title, body, and images from one page response."""
    soup = BeautifulSoup(html, "html.parser")
    title_el = (
        soup.select_one('meta[property="og:title"]')
        or soup.select_one("article h1, main h1, h1")
        or soup.select_one("title")
    )
    title = (_attr(title_el, "content") or _text(title_el))[:300]
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    content = soup.select_one("article, main") or soup.body or soup
    body_text = "\n".join(line.strip() for line in content.get_text("\n").splitlines() if line.strip())
    img_urls = []
    for img in content.select("img")[:20]:
        src = img.get("src") or img.get("data-src") or img.get("data-original")
        normalized = normalize_url(page_url, src)
        if normalized:
            img_urls.append(normalized)
    return title, body_text[:max_text_chars], list(dict.fromkeys(img_urls))


def enrich_article_dom(item: RawItem, user_agent: str = "Mozilla/5.0", max_text_chars: int = 8000) -> tuple[str, str, list[str], str, str]:
    headers = {"User-Agent": user_agent, "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.7"}
    try:
        with httpx.Client(follow_redirects=True, timeout=25.0, headers=headers) as client:
            r = client.get(item.url)
            r.raise_for_status()
        page_url = str(r.url)
        title, body_text, img_urls = extract_page_text(r.text, page_url, max_text_chars)
        if not title or not body_text:
            raise ValueError("page response did not contain both title and body")
        return title, body_text, img_urls, page_url, response_id(r.text)
    except Exception as e:
        raise RuntimeError(f"DOM enrichment failed for {item.url}: {e}") from e
