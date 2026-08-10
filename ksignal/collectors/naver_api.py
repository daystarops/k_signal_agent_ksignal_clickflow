from __future__ import annotations

import hashlib
import os
from html import unescape
from bs4 import BeautifulSoup
import httpx
from ksignal.schema import RawItem


def strip_html(s: str) -> str:
    return BeautifulSoup(unescape(s or ""), "html.parser").get_text(" ", strip=True)


def _endpoint(stype: str) -> str | None:
    if stype == "naver_news_api":
        return "https://openapi.naver.com/v1/search/news.json"
    if stype == "naver_blog_api":
        return "https://openapi.naver.com/v1/search/blog.json"
    if stype == "naver_cafe_api":
        return "https://openapi.naver.com/v1/search/cafearticle.json"
    if stype == "naver_image_api":
        return "https://openapi.naver.com/v1/search/image"
    return None


def collect_naver_search(source: dict, client_id: str | None = None, client_secret: str | None = None) -> list[RawItem]:
    client_id = client_id or os.getenv("NAVER_CLIENT_ID")
    client_secret = client_secret or os.getenv("NAVER_CLIENT_SECRET")
    if not client_id or not client_secret:
        return []
    stype = source["type"]
    endpoint = _endpoint(stype)
    if not endpoint:
        return []
    params = {
        "query": source.get("query", "K리그"),
        "display": int(source.get("display", 10)),
        "sort": source.get("sort", "date"),
    }
    headers = {"X-Naver-Client-Id": client_id, "X-Naver-Client-Secret": client_secret}
    with httpx.Client(timeout=25.0, follow_redirects=True) as client:
        r = client.get(endpoint, params=params, headers=headers)
        r.raise_for_status()
        data = r.json()
    rows: list[RawItem] = []
    for it in data.get("items", []):
        title = strip_html(it.get("title", ""))
        snippet = strip_html(it.get("description", ""))
        url = it.get("originallink") or it.get("link") or ""
        image_urls = []
        if stype == "naver_image_api":
            url = it.get("link", "")
            image_urls = [u for u in [it.get("link"), it.get("thumbnail")] if u]
            snippet = strip_html(it.get("title", ""))
        uid = hashlib.sha1(f"{source.get('name')}|{url}|{title}".encode("utf-8")).hexdigest()[:16]
        rows.append(RawItem(
            id=uid,
            source=source.get("name", "Naver Search"),
            source_family="naver",
            category=source.get("category", "uncategorized"),
            title=title,
            url=url,
            snippet=snippet,
            image_urls=image_urls,
            metadata={"collector": stype, "query": source.get("query"), "naver_sort": params["sort"]}
        ))
    return rows
