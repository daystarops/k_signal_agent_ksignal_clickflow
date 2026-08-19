"""Source-level stabilization wrapper for the recovered Issue builder."""
from __future__ import annotations
import importlib.machinery, importlib.util
from pathlib import Path
import json
from .site_stabilization import stabilize_issue

_PATH = Path(__file__).with_name("issue_builder.pre_watchlist.py")
_LOADER = importlib.machinery.SourceFileLoader("ksignal._issue_builder_pre_watchlist", str(_PATH))
_SPEC = importlib.util.spec_from_loader(_LOADER.name, _LOADER)
_MODULE = importlib.util.module_from_spec(_SPEC); _LOADER.exec_module(_MODULE)
MOBILE_CSS = """
.search-aliases{position:absolute!important;width:1px!important;height:1px!important;padding:0!important;margin:-1px!important;overflow:hidden!important;clip:rect(0,0,0,0)!important;white-space:nowrap!important;border:0!important}
@media(max-width:760px){html,body{max-width:100%;overflow-x:clip}.site-header{padding-left:max(12px,env(safe-area-inset-left));padding-right:max(12px,env(safe-area-inset-right))}.lane-nav{row-gap:4px}.lane-trigger,.search-toggle,.comment-toggle,.pill,.read-signal,.site-footer a,.related-signals-list a,.more-from-issue-list a{min-height:44px}.lane-trigger,.read-signal,.site-footer a,.related-signals-list a,.more-from-issue-list a{display:inline-flex;align-items:center}.search-typeahead a{min-height:48px}.article-body p a:not(.pill){display:inline;padding:10px 3px;margin:-10px -3px;line-height:2.55;box-decoration-break:clone;-webkit-box-decoration-break:clone}.article-head h1{font-size:clamp(30px,9.4vw,36px);overflow-wrap:anywhere}.article-head .dek{font-size:clamp(16px,4.6vw,17px)!important}.hero img,.story-preview img{max-width:100%;object-fit:cover}.embed{overflow:hidden}.receipts .pill{display:inline-flex;align-items:center}.comment-panel input,.comment-panel textarea,.search-form input{font-size:16px}.related-signals-list,.more-from-issue-list{overscroll-behavior-inline:contain;scroll-snap-type:none}.site-footer nav{align-items:center}.site-footer p{white-space:normal}}
@media(max-width:340px){.site-header{padding-left:8px;padding-right:8px}.brand img{width:124px}.lane-nav{gap:2px}.lane-trigger{font-size:9px;padding-left:2px;padding-right:2px}.home-shell,.article-shell,.policy-shell{margin-left:4px;margin-right:4px}.article-shell{padding-left:10px;padding-right:10px}.story-preview.supporting{grid-template-columns:88px minmax(0,1fr)}.site-search.is-open{width:calc(100vw - 16px);right:8px}.search-typeahead{left:8px;right:8px}}
"""
_MODULE.CSS += MOBILE_CSS; _MODULE._I.CSS = _MODULE.CSS
for _name, _value in vars(_MODULE).items():
    if not _name.startswith("__"): globals()[_name] = _value

def transform_card(card: SignalCard) -> EditorialCard:
    override = next(
        (value for key, value in EDITORIAL_OVERRIDES.items() if key in card.url),
        None,
    )
    if override is None:
        override = {
            "title": _compact(card.title_english or card.title_original, LIMITS["title"]),
            "lane": "fandom" if card.category == "idols" else card.category.replace("_", " "),
            "heard_in_feed": _compact(card.cultural_read, LIMITS["heard"]),
            "english_translation": _compact(card.literal_translation, LIMITS["english"]),
            "comments_read": "",
            "why_it_has_legs": _compact(card.business_read, LIMITS["legs"]),
            "watch_next": (card.tags + ["반응", "맥락", "다음"])[:5],
        }

    editorial = EditorialCard(
        source=card.source,
        url=card.url,
        source_type="global_reaction" if "reddit.com" in card.url else "korean_native",
        korean_quote=_compact(card.raw_korean_excerpt, LIMITS["korean"]),
        **override,
    )
    errors = validate_editorial_card(editorial, require_media=False)
    if errors:
        raise ValueError("; ".join(errors))
    return editorial

_MODULE._I.transform_card = transform_card
_MODULE.transform_card = transform_card
_before = _MODULE._I._write_editorial_issue
def _write_editorial_issue(editorial, issue, output_root, require_media):
    result = _before(editorial, issue, output_root, require_media)
    issue_dir = Path(output_root) / issue
    stabilize_issue(issue_dir)
    _project_public_article_paths(issue_dir)
    return result


def _project_public_article_paths(issue_dir: Path) -> None:
    """Rename slot-addressed legacy pages to ArticlePackage public slugs."""
    pairs: list[tuple[str, str]] = []
    package_dir = issue_dir / "article_packages"
    if not package_dir.is_dir():
        return
    from .article_package import ArticlePackage

    for package_path in sorted(package_dir.glob("*.json")):
        package = ArticlePackage.model_validate_json(package_path.read_text(encoding="utf-8"))
        pairs.append((package.editorial_slot, package.article_slug))
    for slot, slug in pairs:
        source = issue_dir / "articles" / f"{slot}.html"
        target = issue_dir / "articles" / f"{slug}.html"
        if source != target:
            if source.exists():
                source.replace(target)
            elif not target.exists():
                raise ValueError(f"Generated article path is missing: {source}")
    replacements = [(f"articles/{slot}.html", f"articles/{slug}.html") for slot, slug in pairs]
    replacements += [(f'{slot}.html', f'{slug}.html') for slot, slug in pairs]
    for html_path in issue_dir.rglob("*.html"):
        html = html_path.read_text(encoding="utf-8")
        updated = html
        for old, new in replacements:
            updated = updated.replace(old, new)
        if updated != html:
            html_path.write_text(updated, encoding="utf-8")
_MODULE._I._write_editorial_issue = _write_editorial_issue


def rebuild_issue(
    issue: str,
    output_root: str | Path = "outputs/issues",
    allow_unknown_rights: bool = False,
) -> tuple[Path, Path]:
    """Rebuild from editorial rows and the selected-media manifest."""
    issue_dir = Path(output_root) / issue
    rows = json.loads((issue_dir / "editorial_cards.json").read_text(encoding="utf-8"))
    manifest_path = issue_dir / "media" / "media_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    for index in range(1, len(rows) + 1):
        media = manifest.get(str(index), {})
        if not media.get("hero_image_path") and not media.get("video_url"):
            raise ValueError(f"Card {index} media selection is unresolved; rebuild aborted.")
    cards = []
    for index, row in enumerate(rows, 1):
        media = manifest.get(str(index), {})
        override = next(
            (value for key, value in EDITORIAL_OVERRIDES.items() if key in row.get("url", "")),
            None,
        )
        if override:
            row.update(override)
        rights = media.get("rights_status", row.get("media_rights_status", "unknown"))
        if rights == "unknown" and not allow_unknown_rights:
            raise ValueError(
                f"Card {index} uses unknown-rights fallback media; "
                "pass --allow-unknown-rights to override."
            )
        is_historical_card_one = "4059776426" in row.get("url", "")
        selected_video = "" if is_historical_card_one else media.get("video_url", "")
        selected_thumbnail = "" if is_historical_card_one else media.get(
            "video_thumbnail_path", ""
        )
        if is_historical_card_one:
            media["media_reason"] = "Still image from the source post"
        backup = selected_video or row.get("backup_url", "") or media.get("hero_source_url", "")
        row.update(
            hero_image_path=media.get("hero_image_path", row.get("hero_image_path", "")),
            hero_image_source_url=media.get(
                "hero_source_url", row.get("hero_image_source_url", "")
            ),
            hero_caption=media.get("media_reason", row.get("hero_caption", "")),
            video_url=selected_video,
            video_embed_url=selected_video,
            video_click_url=_normalize_video_click(selected_video),
            video_thumbnail_path=selected_thumbnail,
            media_type="video" if selected_video else "image",
            media_confidence=media.get("media_confidence", row.get("media_confidence", "low")),
            backup_url=backup,
            media_rights_status=rights,
        )
        cards.append(EditorialCard.model_validate(row))
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return _write_editorial_issue(cards, issue, output_root, require_media=True)
