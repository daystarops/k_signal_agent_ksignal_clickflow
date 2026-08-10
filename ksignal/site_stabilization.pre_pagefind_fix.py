"""Stable public-site normalization around the recovered Issue builder."""
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

CARD_ALIASES = {
    "card_01": ["K-pop", "케이팝", "K팝", "팬덤", "해외팬", "외국팬", "글로벌 팬덤", "韓流", "한류"],
    "card_02": ["Billlie", "빌리", "Billie", "Work", "워크", "Zap", "잽", "팬덤", "컴백", "소속사", "agency", "comeback"],
    "card_03": ["K League", "K리그", "케이리그", "축구", "국내축구", "starter pack", "입문", "가이드", "guide"],
    "card_04": ["Lingard", "린가드", "FC Seoul", "FC서울", "서울", "K League", "K리그", "축구", "상암", "월드컵경기장"],
}
LANE_ALIASES = {
    "Beauty": ["뷰티", "미용", "피부", "스킨케어", "美容", "美妆", "ビューティー"],
    "Society": ["사회", "생활", "정책", "주거", "일", "社会", "社會", "社会問題"],
    "Fandom": ["팬덤", "팬", "아이돌", "케이팝", "K팝", "推し", "粉丝"],
    "Sports": ["스포츠", "축구", "야구", "K리그", "スポーツ", "体育", "體育"],
    "Food": ["푸드", "음식", "맛집", "카페", "편의점", "食べ物", "グルメ", "美食"],
}

def _unique(values: list[str]) -> list[str]:
    seen, result = set(), []
    for value in values:
        key = unicodedata.normalize("NFKC", value).casefold()
        if key not in seen:
            seen.add(key)
            result.append(value)
    return result

def enrich_search_indexes(issue_dir: Path) -> None:
    search_dir = issue_dir / "search"
    cards_path = search_dir / "cards_index.json"
    if not cards_path.exists():
        return
    cards = json.loads(cards_path.read_text(encoding="utf-8"))
    for card in cards:
        aliases = _unique(CARD_ALIASES.get(card["card_id"], []) + LANE_ALIASES.get(card["lane"], []))
        card["search_aliases"] = aliases
        card["search_keywords"] = _unique(list(card.get("search_keywords", [])) + aliases)
        normalized = [unicodedata.normalize("NFKC", item).casefold() for item in aliases]
        card["normalized_search_text"] = " ".join([card.get("normalized_search_text", ""), *normalized]).strip()
    cards_path.write_text(json.dumps(cards, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lanes_path = search_dir / "lanes_index.json"
    lanes = json.loads(lanes_path.read_text(encoding="utf-8"))
    for lane, aliases in LANE_ALIASES.items():
        for alias in aliases:
            lanes.setdefault(alias, list(lanes.get(lane, [])))
    lanes_path.write_text(json.dumps(lanes, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for filename in ("topics_index.json", "entities_index.json"):
        path = search_dir / filename
        index = json.loads(path.read_text(encoding="utf-8"))
        for card_id, aliases in CARD_ALIASES.items():
            for alias in aliases:
                bucket = index.setdefault(alias, [])
                if card_id not in bucket:
                    bucket.append(card_id)
        path.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

def _metadata_block(card_ids: list[str]) -> str:
    aliases = _unique([alias for card_id in card_ids for alias in CARD_ALIASES.get(card_id, [])])
    return f'<div class="search-aliases" aria-hidden="true" data-pagefind-body data-pagefind-meta="aliases">{" · ".join(aliases)}</div>'

def stabilize_html(issue_dir: Path) -> None:
    assets = issue_dir / "assets"
    assets.mkdir(exist_ok=True)
    interaction_js = None
    script_pattern = re.compile(r"<script>(\(\(\)=>\{.*?\}\)\(\);?)</script>", re.DOTALL)
    for path in sorted(issue_dir.rglob("*.html")):
        if "host_package" in path.parts or "social" in path.parts:
            continue
        html = path.read_text(encoding="utf-8")
        match = script_pattern.search(html)
        if match:
            interaction_js = interaction_js or match.group(1)
            prefix = "../" if path.parent.name == "articles" else ""
            html = html[:match.start()] + f'<script src="{prefix}assets/ksignal.js" defer></script>' + html[match.end():]
        card_match = re.search(r"card_(?:01|02|03|04)", path.stem)
        if card_match and "search-aliases" not in html:
            html = html.replace("</main>", _metadata_block([card_match.group(0)]) + "</main>", 1)
        elif path.name == "newsletter.html" and "search-aliases" not in html:
            html = html.replace("</main>", _metadata_block(list(CARD_ALIASES)) + "</main>", 1)
        if "youtube.com/embed/" in html:
            html = html.replace('title="Embedded video"', 'title="Billlie — Work performance video on YouTube"')
            html = html.replace(' loading="lazy" allow=', ' loading="lazy" referrerpolicy="strict-origin-when-cross-origin" allow=')
            html = html.replace("accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture", "accelerometer; encrypted-media; gyroscope; picture-in-picture")
            html = html.replace("Embed not loading?", "YouTube video · Embed not loading?")
        html = html.replace('<p class="honeypot">', '<p class="honeypot" hidden aria-hidden="true">')
        html = html.replace('<select id="lane-filters">', '<select id="lane-filters" aria-label="Filter search results by lane">')
        html = html.replace('<i>▶</i>', '<i aria-hidden="true">▶</i>')
        path.write_text(html, encoding="utf-8")
    if interaction_js:
        (assets / "ksignal.js").write_text(interaction_js + "\n", encoding="utf-8")

def stabilize_issue(issue_dir: str | Path) -> None:
    issue_path = Path(issue_dir)
    enrich_search_indexes(issue_path)
    stabilize_html(issue_path)
