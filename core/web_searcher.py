from __future__ import annotations

import json
import re
from urllib.parse import quote_plus, urlparse

REJECT = re.compile(r"(?:logo|avatar|profile|icon|emoji|sprite|stock|advert|placeholder)", re.I)
OFFICIAL_HINTS = ("official", "youtube.com", "sports", "news", "entertain", "instagram.com")


def _score(url: str, page_url: str, title: str, width: int, height: int, query: str) -> tuple[float, str]:
    haystack = f"{url} {page_url} {title}".lower()
    terms = {term.lower() for term in re.findall(r"[A-Za-z0-9가-힣]+", query) if len(term) > 2}
    overlap = sum(term in haystack for term in terms) / max(1, min(5, len(terms)))
    score = .42 + min(.28, overlap * .35)
    reasons = ["search result matches the card topic"]
    if width >= 1000 or height >= 700:
        score += .18; reasons.append("large image")
    elif width >= 500 or height >= 350:
        score += .10
    if any(hint in haystack for hint in OFFICIAL_HINTS):
        score += .08; reasons.append("official/contextual source")
    if REJECT.search(haystack) or width and width < 300 or height and height < 180:
        score -= .55; reasons.append("small or likely non-editorial asset")
    return round(max(0, min(.95, score)), 2), "; ".join(reasons)


def search_media(page, query: str, video_relevant: bool = False, max_results: int = 12) -> list[dict]:
    """Search public Bing/Naver/YouTube pages through the provided Playwright page."""
    candidates = []
    searches = [f"https://search.naver.com/search.naver?where=nexearch&query={quote_plus(query)}", f"https://search.naver.com/search.naver?where=image&query={quote_plus(query)}", f"https://www.bing.com/images/search?q={quote_plus(query)}"]
    for search_url in searches:
        try:
            page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(1200)
            rows = page.evaluate("""() => Array.from(document.querySelectorAll('a.iusc, a[href] img')).slice(0,40).map(node => {
              const a=node.matches('a')?node:node.closest('a'); const img=node.matches('img')?node:node.querySelector('img');
              let meta={}; try { meta=JSON.parse(a?.getAttribute('m')||'{}') } catch(e) {}
              return {media_url:meta.murl||img?.currentSrc||img?.src||'',page_url:meta.purl||a?.href||'',title:meta.t||img?.alt||'',width:meta.w||img?.naturalWidth||0,height:meta.h||img?.naturalHeight||0};
            }).filter(x => x.media_url)""")
            for row in rows:
                score, reason = _score(row["media_url"], row["page_url"], row["title"], int(row["width"] or 0), int(row["height"] or 0), query)
                candidates.append({**row, "source_domain": urlparse(row["page_url"]).netloc.lower(), "type": "image", "relevance_score": score, "reason": reason})
        except Exception:
            continue
    if video_relevant:
        try:
            page.goto(f"https://www.youtube.com/results?search_query={quote_plus(query)}", wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(1200)
            rows = page.evaluate("""() => Array.from(document.querySelectorAll('a#video-title')).slice(0,8).map(a => ({url:a.href,title:a.title||a.textContent.trim()})).filter(x=>x.url)""")
            for row in rows:
                video_id = re.search(r"[?&]v=([^&]+)", row["url"])
                score, reason = _score(row["url"], row["url"], row["title"], 1280, 720, query)
                candidates.append({"media_url": row["url"], "page_url": row["url"], "title": row["title"], "source_domain": "youtube.com", "width": 1280, "height": 720, "type": "video", "relevance_score": score, "reason": reason})
                if video_id:
                    candidates.append({"media_url": f"https://i.ytimg.com/vi/{video_id.group(1)}/maxresdefault.jpg", "page_url": row["url"], "title": row["title"], "source_domain": "youtube.com", "width": 1280, "height": 720, "type": "thumbnail", "relevance_score": score, "reason": "thumbnail for relevant YouTube result"})
        except Exception:
            pass
    unique = {}
    for row in candidates:
        if not REJECT.search(f"{row['media_url']} {row['title']}") and (row["media_url"] not in unique or row["relevance_score"] > unique[row["media_url"]]["relevance_score"]):
            unique[row["media_url"]] = row
    return sorted(unique.values(), key=lambda row: row["relevance_score"], reverse=True)[:max_results]
