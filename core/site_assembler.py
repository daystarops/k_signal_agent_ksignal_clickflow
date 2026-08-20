"""Assemble immutable issue outputs into one persistent static publication."""

from __future__ import annotations

import copy
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from core.host_packager import NETLIFY_HEADERS, validate_host_package


PUBLIC_PAGES = ("about.html", "contact.html", "privacy.html", "accessibility.html", "terms.html")
# A canonical URL only does its job as an absolute address, and the package itself is deliberately
# relative so it can be mounted anywhere, so the origin has to be supplied rather than inferred.
# This mirrors `DEFAULT_PUBLIC_ISSUE_URL` in core/distribution_pack.py, which is the origin this
# publication already distributes; `SITE_BASE_URL` overrides it per build.
DEFAULT_SITE_BASE_URL = "https://read-ksignal.netlify.app"
PUBLIC_DIRS = ("assets", "media")
ISSUE_METADATA: dict[str, dict[str, str]] = {
    "001": {"date": "2026-08-09"},
    "002": {"date": "2026-08-23"},
}

# The persistent site re-projects issue_builder's lane interaction onto every staged copy of
# assets/ksignal.js. Width alone cannot decide touch behaviour, so the capability query replaces
# the phone-width query, and the mobile popover is anchored to its trigger instead of inheriting
# the shared `.lane-popover{top:100%}` rule.
INTERACTION_SOURCE = "const mobile=()=>matchMedia('(max-width:760px)').matches"
INTERACTION_TARGET = "const mobile=()=>matchMedia('(hover:none), (pointer:coarse)').matches"
POPOVER_SOURCE = "item.classList.add('is-open');button.setAttribute('aria-expanded','true')"
# The phone popover is anchored with an inline top. Above the phone breakpoint it must be cleared,
# otherwise a value measured at 390px keeps overriding the tablet/desktop anchor rule and leaves the
# popover detached from its trigger after a rotation or resize.
POPOVER_TARGET = (
    "item.classList.add('is-open');button.setAttribute('aria-expanded','true');"
    "{const popover=item.querySelector('.lane-popover');"
    "if(popover)popover.style.top=matchMedia('(max-width:760px)').matches?"
    "`${Math.ceil(button.getBoundingClientRect().bottom+6)}px`:''}"
)
# A popover left open across a rotation never re-runs the open handler, so drop the stale value as
# soon as the viewport leaves the phone regime.
POPOVER_RESIZE_RESET = (
    ";addEventListener('resize',()=>{if(!matchMedia('(max-width:760px)').matches)"
    "document.querySelectorAll('.lane-popover').forEach(p=>{p.style.top=''})});"
)
INTERACTION_MARKERS = (
    "matchMedia('(hover:none), (pointer:coarse)')",
    "button.getBoundingClientRect().bottom+6",
    "document.querySelectorAll('.lane-popover').forEach(p=>{p.style.top=''})",
)
SITE_RESPONSIVE_CSS = """
.preview-media iframe{display:block;width:100%;height:100%;border:0}
.lane-item.is-open .lane-popover{opacity:1!important;visibility:visible!important;pointer-events:auto!important;transform:translateY(0)!important}
.archive-list{list-style:none;margin:28px 0 0;padding:0;border-top:1px solid var(--line)}
.archive-list li{display:flex;align-items:baseline;justify-content:space-between;gap:24px;padding:18px 0;border-bottom:1px solid var(--line)}
.archive-list a{color:var(--navy);font:700 22px/1.2 Georgia,serif;text-decoration:none}
.archive-list a:hover,.archive-list a:focus{text-decoration:underline;text-decoration-color:var(--red);text-underline-offset:4px}
.archive-list time{color:var(--muted);font-size:12px;white-space:nowrap}
@media(max-width:1200px){
  /* The stacked header and the centred lane row are now the base layout, so this query only
     carries what is still width-specific: the full-bleed header box and touch-sized triggers. */
  .site-header{margin-top:0;max-width:none;padding:12px 20px 0}
  .lane-trigger{min-height:44px;cursor:pointer}
  /* The centred, wrapped lane row moves the first lane far enough left that a right-anchored
     240px popover resolves to a negative left edge at 761-880px. Anchor that one inward. */
  .lane-item:first-child .lane-popover{right:auto;left:0}
  .front-page{grid-template-columns:minmax(0,1.2fr) minmax(280px,1fr);grid-template-areas:"lead secondary" "supporting supporting";gap:28px}
  .story-preview.lead{padding-right:24px}
  .supporting-stack{grid-template-columns:repeat(2,minmax(0,1fr));gap:24px;border-top:1px solid var(--line);padding-top:4px}
  .story-preview.supporting{display:block;grid-template-columns:none}
  .story-preview.supporting .hero{aspect-ratio:16/9}
  .story-preview.supporting .preview-copy{width:100%;padding-top:14px}
}
@media(max-width:760px){
  .front-page{display:block}
  .supporting-stack{display:block;border-top:0;padding-top:0}
  .story-preview.supporting{display:block;grid-template-columns:none}
  .story-preview.supporting .preview-copy{width:100%;padding-top:14px}
  .story-preview .hero{width:100%;aspect-ratio:16/9;margin-bottom:0}
  .lane-popover{z-index:80}
  .archive-list li{display:block}
  .archive-list time{display:block;margin-top:6px}
}
"""

# The in-article interpretive layer carries no class of its own in issue_builder output, so it is
# matched on its heading and given one. Compared case-folded and whitespace-collapsed because the
# heading is title-cased on the page but written in sentence case elsewhere.
INTERNET_READ_HEADING = "what the internet is really saying"

# Presentation pass. Injected after SITE_RESPONSIVE_CSS so it settles the cascade for the rules it
# restates, and written against the existing tokens (--navy/--line/--surface) and breakpoints
# (1200/760/340) rather than a second design system.
SITE_PRESENTATION_CSS = """
/* Masthead: logo far left, Subscribe then Search on the right, lane row on its own line.
   Only padding-bottom is claimed here; the width-specific left/right padding, including the
   phone safe-area insets, stays with the rules that already own it. */
.site-header{display:block;padding-bottom:0}
.header-main{display:flex;align-items:center;justify-content:space-between;gap:24px;padding-bottom:12px}
.brand{flex:0 0 auto;margin-right:auto}
.header-actions{display:flex;align-items:center;justify-content:flex-end;flex:0 0 auto;gap:12px}

/* The lane row is a full-width block inside a header whose horizontal padding is symmetric and
   whose box is centred by `margin:auto`. Centring the flex line therefore centres the group on
   the page axis at every width, with no fixed offset to break on the next viewport. */
.lane-nav{display:flex;width:100%;justify-content:center;align-items:center;flex-wrap:wrap;gap:8px 16px;margin:0;padding:10px 0 11px;border-top:1px solid var(--line)}
.lane-trigger{box-shadow:none}

/* Search is the furthest-right control and reads as one rounded container in both its collapsed
   and expanded states, so the inner form and toggle drop their own opaque backgrounds. */
.site-search{border:1px solid #1018282e;border-radius:999px;box-shadow:none;background:var(--surface);transition:width .2s ease,border-color .16s ease,box-shadow .16s ease}
.site-search:hover{border-color:#10182852}
.site-search:focus-within{border-color:var(--navy);box-shadow:0 0 0 3px #10182812}
.search-form{background:transparent;border-radius:999px}
.search-form input{background:transparent;padding-right:16px}
.search-toggle{background:transparent;border-radius:999px}
.search-typeahead{border-radius:12px;overflow:hidden;box-shadow:0 12px 28px #10182814}

/* Subscribe is presentation-only: this repo has no signup mechanism to wire it to, so it is
   announced as unavailable rather than promising a destination that does not exist. A flat black
   rectangle, square-cornered, so Search stays the only rounded control in the masthead. */
.subscribe-control{appearance:none;display:inline-flex;align-items:center;min-height:40px;padding:0 16px;border:0;border-radius:0;background:#000;color:#fff;font:800 11px/1 Arial,sans-serif;letter-spacing:.09em;text-transform:uppercase;white-space:nowrap}
.subscribe-control:focus-visible{outline:2px solid var(--navy);outline-offset:2px}
.subscribe-control[aria-disabled="true"]{cursor:default}

/* An interpretive layer inside the article. The rail belongs to the whole module — heading and
   body together — not to the heading alone, which is what made it read as a heading with a
   decoration rather than as a marked passage. Flat: no card border, no shadow, square corners,
   no panel tint. The heading is a utility label, deliberately not a second article headline;
   `.article-body h2` is already 11px uppercase, so this one separates itself by weight, colour
   and tracking instead of by size. Body copy stays at the article's normal reading size. A navy
   tint, kept far enough down that it separates the passage without becoming a card, sits under
   the whole module. */
.article-body .internet-read{margin:28px 0;padding:12px 16px;border:0;border-left:3px solid var(--red);border-radius:0;background:#16305e0a;box-shadow:none}
.article-body .internet-read h2{margin:0 0 8px;border-left:0;padding-left:0;color:var(--red);font:800 11px/1.25 Arial,sans-serif;letter-spacing:.13em;text-transform:uppercase}
.article-body .internet-read p{margin:0 0 1.15em;font-size:18px;line-height:1.65}
.article-body .internet-read p:last-child{margin-bottom:0}

@media(max-width:760px){
  .header-main{gap:10px;padding-bottom:10px}
  .header-actions{gap:8px}
  .subscribe-control{min-height:44px;padding:0 12px;font-size:10px;letter-spacing:.06em}
  .lane-nav{gap:6px 10px;padding:8px 0 9px}
  .article-body .internet-read{margin-top:24px;padding:12px 13px}
}
/* Phone lane density. The five controls, their order and their rectangular language are the
   approved header; only the space around them is claimed back, so the first story starts higher
   without the row losing a control or dropping below a 44px touch target.

   Wrapping the five lanes onto two lines spent a second row of header on a control strip and left
   a ragged half-row under it. On a phone they become one scrolling line instead: every lane keeps
   its full Korean and English label and its own content width, the row starts on the same inset as
   the rest of the header rather than centred, and the overflow is the row's to scroll, never the
   page's. No arrows and no carousel — the strip is a list the thumb moves, which is why the
   scrollbar is hidden where the browser allows it while the scrolling itself stays untouched.
   The popover is `position:fixed` at this width, so it is not clipped by the scroll container. */
@media(max-width:640px){
  .lane-nav{flex-wrap:nowrap;justify-content:flex-start;gap:8px;padding:5px 0 6px;overflow-x:auto;overflow-y:hidden;-webkit-overflow-scrolling:touch;scrollbar-width:none;-ms-overflow-style:none}
  .lane-nav::-webkit-scrollbar{display:none}
  .lane-item{flex:0 0 auto}
  .lane-trigger{padding:4px 8px;white-space:nowrap}
}
@media(max-width:340px){
  .header-actions{gap:6px}
  .subscribe-control{padding:0 9px;letter-spacing:.04em}
}
"""

# Homepage foundations, generated with the Utopia fluid-responsive method rather than a desktop
# size that swaps at a breakpoint. Measured basis on this site before the pass: body copy was
# 16px below 760 and 18px above it, and the desktop content column is 1200px wide. The fluid range
# is therefore 390px (narrow modern phone) -> 1200px (the site's actual desktop content width),
# ratio 1.2 at the minimum and 1.25 at the maximum. Grid TOPOLOGY still steps at 1024/640, because
# a four-column front is a different composition from a one-column one; type and spacing breathe
# continuously between those steps.
HOME_TOKENS_CSS = """
.home-shell{
  --step--2:clamp(0.6944rem,0.6821rem + 0.0505vw,0.72rem);
  --step--1:clamp(0.8333rem,0.8077rem + 0.1049vw,0.9rem);
  --step-0:clamp(1rem,0.9538rem + 0.1893vw,1.125rem);
  --step-1:clamp(1.2rem,1.1245rem + 0.3097vw,1.4063rem);
  --step-2:clamp(1.44rem,1.3231rem + 0.4795vw,1.7583rem);
  --step-3:clamp(1.728rem,1.5528rem + 0.7186vw,2.1975rem);
  --space-3xs:clamp(0.25rem,0.2423rem + 0.0316vw,0.2813rem);
  --space-2xs:clamp(0.5rem,0.4769rem + 0.0947vw,0.5625rem);
  --space-xs:clamp(0.75rem,0.7154rem + 0.142vw,0.8438rem);
  --space-s:clamp(1rem,0.9538rem + 0.1893vw,1.125rem);
  --space-m:clamp(1.5rem,1.4308rem + 0.284vw,1.6875rem);
  --gap-column:clamp(1rem,0.6154rem + 1.5779vw,2.0625rem);
  --gap-row:clamp(1.25rem,0.9808rem + 1.1045vw,2rem);
  --gap-package:clamp(2.5rem,1.9077rem + 2.4299vw,4.125rem);
}
"""

# Homepage composition. A front page over every publishable story: one editorial pool, roles that
# decide geometry AND what each story suppresses, and two named packages. Nothing here is keyed to
# an issue. The issue pages keep `.front-page` and their own layout untouched.
HOME_CSS = """
.home-vh{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
.home-masthead{border-top:2px solid var(--navy);padding-top:var(--space-xs);margin-bottom:var(--space-m);display:flex;align-items:baseline;justify-content:space-between;gap:var(--space-s);flex-wrap:wrap}
.home-standfirst{margin:0;font:italic 400 var(--step--1)/1.3 Georgia,serif;color:var(--muted)}
.home-datestamp{margin:0;font:700 var(--step--2)/1 Arial,sans-serif;letter-spacing:.1em;text-transform:uppercase;color:var(--muted)}

.home-pkg-head{display:flex;align-items:baseline;gap:var(--space-s);margin-bottom:var(--space-s)}
.home-pkg-label{margin:0;font:800 var(--step--2)/1 Arial,sans-serif;letter-spacing:.12em;text-transform:uppercase;color:var(--navy)}
.home-pkg-label::before{content:"";display:inline-block;width:18px;height:3px;background:var(--red);margin-right:10px;vertical-align:middle}

.home-story{min-width:0;display:flex;flex-direction:column;gap:var(--space-2xs);background:transparent}
.home-media{position:relative;display:block;aspect-ratio:var(--ratio,16/9);overflow:hidden;background:#e6e8ea}
.home-media img{width:100%;height:100%;object-fit:cover;display:block}
.home-play{position:absolute;inset:0;display:grid;place-items:center;pointer-events:none}
.home-play svg{width:clamp(30px,12%,44px);height:auto}
.home-copy{display:flex;flex-direction:column;gap:var(--space-3xs);min-width:0}
/* Every picture role also has a text-only projection, because a role is a position and printable
   media is a property of the story. With no picture beside it the copy owns the whole row rather
   than sitting in the width the absent thumbnail was holding. */
.home-copy:only-child{grid-column:1/-1}
.home-lane{margin:0;font:800 var(--step--2)/1 Arial,sans-serif;letter-spacing:.04em;color:var(--red)}
.home-head{margin:0;font-family:Georgia,serif;font-weight:700;line-height:1.14;font-size:var(--step-1);letter-spacing:-.005em}
.home-head a{color:var(--navy);text-decoration:none}
.home-head a:hover,.home-head a:focus{text-decoration:underline;text-decoration-color:var(--red);text-underline-offset:4px}
.home-dek{margin:var(--space-3xs) 0 0;font:400 var(--step-0)/1.45 Georgia,serif;color:var(--muted)}

.home-story[data-role="lead"] .home-head{font-size:var(--step-3);line-height:1.06}
.home-story[data-role="lead"] .home-dek{font-size:var(--step-1);line-height:1.4}
.home-story[data-role="feature"] .home-head{font-size:var(--step-2)}
.home-story[data-role="vertical"] .home-dek{font-size:var(--step--1);line-height:1.4}
.home-story[data-role="horizontal"]{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,2fr);gap:var(--space-s);align-items:start;border-top:1px solid var(--line);padding-top:var(--space-xs)}
.home-story[data-role="compact"]{border-top:1px solid var(--line);padding-top:var(--space-xs)}
.home-story[data-role="compact"] .home-head{font-size:var(--step-0);line-height:1.25}

.home-package{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));column-gap:var(--gap-column);row-gap:var(--gap-row)}
.home-package--front>[data-slot="0"]{grid-column:span 2;grid-row:span 3}
.home-package--front>[data-slot="3"],.home-package--front>[data-slot="4"]{grid-column:span 2}
.home-package--more>[data-slot="0"],.home-package--more>[data-slot="1"]{grid-column:span 2}
.home-rows{grid-column:span 4;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));column-gap:var(--gap-column);row-gap:var(--gap-row);align-content:start}
.home-more{margin-top:var(--gap-package);padding-top:var(--space-m);border-top:1px solid var(--navy)}

/* An issue route is an archived edition, not an old homepage. Without a stated way back it is a
   navigation trap: the logo is the only exit, and nothing on the page says the reader has stepped
   out of the current publication. */
.edition-bar{display:flex;align-items:baseline;justify-content:space-between;gap:16px;flex-wrap:wrap;margin:0 0 18px;padding-bottom:12px;border-bottom:1px solid var(--line)}
.edition-bar a{color:var(--navy);text-decoration:none;border-bottom:1px solid var(--line)}
.edition-bar a:hover,.edition-bar a:focus{border-bottom-color:var(--red)}
.edition-home{font:800 12px/1.2 Arial,sans-serif;letter-spacing:.06em;text-transform:uppercase;border-bottom:0!important}
.edition-home:hover,.edition-home:focus{text-decoration:underline;text-decoration-color:var(--red);text-underline-offset:4px}
.edition-note{margin:0;color:var(--muted);font:600 11px/1.4 Arial,sans-serif;letter-spacing:.08em;text-transform:uppercase}

@media(min-width:640px){
  /* A row thumbnail is a marker, not a picture slot: the measured reference thumbs are 85-220px,
     never a third of the row, so the headline stays the subject at every width. */
  .home-story[data-role="horizontal"]{grid-template-columns:clamp(96px,16%,168px) minmax(0,1fr)}
}
@media(min-width:640px) and (max-width:1023px){
  .home-package{grid-template-columns:repeat(2,minmax(0,1fr))}
  .home-package--front>[data-slot="0"]{grid-column:span 2;grid-row:auto}
  .home-package--front>[data-slot="0"] .home-story{display:grid;grid-template-columns:minmax(0,1.15fr) minmax(0,1fr);column-gap:var(--gap-column);align-items:start}
  .home-package--front>[data-slot="0"] .home-media{grid-row:span 3}
  .home-package--front>[data-slot="3"],.home-package--front>[data-slot="4"]{grid-column:span 2}
  .home-package--more>[data-slot="0"],.home-package--more>[data-slot="1"]{grid-column:span 1}
  .home-rows{grid-column:span 2}
}
@media(max-width:639px){
  /* Phone projection, following the reference's own collapse: the lead keeps its picture and its
     dek, and everything after it becomes a 33/67 row led by the headline. */
  .home-package{grid-template-columns:minmax(0,1fr)}
  .home-package>[data-slot]{grid-column:span 1}
  .home-rows{grid-column:span 1;grid-template-columns:minmax(0,1fr)}
  .home-story[data-role="vertical"],.home-story[data-role="feature"]{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,2fr);gap:var(--space-s);align-items:start;border-top:1px solid var(--line);padding-top:var(--space-xs)}
  .home-story[data-role="vertical"] .home-media,.home-story[data-role="feature"] .home-media{aspect-ratio:1/1}
  .home-story[data-role="vertical"] .home-dek,.home-story[data-role="feature"] .home-dek{display:none}
  .home-story[data-role="vertical"] .home-head,.home-story[data-role="feature"] .home-head{font-size:var(--step-1)}
}
"""


def _pagefind_page_count(output: str) -> int:
    match = re.search(r"\bIndexed\s+(\d+)\s+pages\b", output)
    return int(match.group(1)) if match else 0


@dataclass(frozen=True)
class SiteBuild:
    site_dir: Path
    issue_routes: tuple[str, ...]
    article_routes: tuple[str, ...]
    pagefind_entry_count: int


def _remove_tree(path: Path) -> None:
    def retry(function, target, _error):
        Path(target).chmod(stat.S_IWRITE)
        function(target)

    shutil.rmtree(path, onerror=retry)


def _write_soup(path: Path, soup: BeautifulSoup) -> None:
    for link in soup.select("a[href]"):
        parsed = urlparse(str(link.get("href", "")))
        if parsed.scheme in {"http", "https"}:
            link["target"] = "_blank"
            link["rel"] = "noopener noreferrer"
    path.write_text(str(soup), encoding="utf-8")


def _issue_date(issue: str) -> str:
    value = str(ISSUE_METADATA.get(issue, {}).get("date", ""))
    if not value:
        raise ValueError(
            f"Issue {issue} has no publication date. Add ISSUE_METADATA[\"{issue}\"] = "
            '{"date": "YYYY-MM-DD"} in core/site_assembler.py before assembling the site.'
        )
    return value


def _set_issue_date(soup: BeautifulSoup, issue: str) -> None:
    value = _issue_date(issue)
    node = soup.select_one(".issue-date time")
    if node is None:
        raise ValueError(f"Issue {issue} newsletter has no '.issue-date time' node to correct")
    parsed = date.fromisoformat(value)
    node["datetime"] = value
    node.string = f"{parsed.strftime('%A, %B')} {parsed.day}, {parsed.year}"


def _project_preview_media(soup: BeautifulSoup, issue_dir: Path, issue: str) -> int:
    """Project the issue's already-approved selected media into its assembled previews.

    Previews that arrive with their own hero are left untouched, so an issue whose markup already
    carries media needs no manifest. Any preview that arrives without one must resolve to approved
    media: a missing manifest, package mapping, or media entry is the zero-media release defect and
    fails the build rather than shipping a preview-less page.
    """
    pending = [
        preview
        for preview in soup.select("article.story-preview")
        if preview.select_one("h2 a[href]") and not preview.select_one(".hero")
    ]
    if not pending:
        return 0
    manifest_path = issue_dir / "media" / "media_manifest.json"
    package_dir = issue_dir / "article_packages"
    if not manifest_path.exists():
        raise FileNotFoundError(
            f"Issue {issue}: {len(pending)} preview(s) have no hero and there is no selected-media "
            f"manifest at {manifest_path}"
        )
    if not package_dir.is_dir():
        raise FileNotFoundError(
            f"Issue {issue}: selected-media manifest exists but {package_dir} is missing, so approved "
            "media cannot be mapped to story slugs"
        )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    by_slug: dict[str, dict] = {}
    for package_path in sorted(package_dir.glob("card_*.json")):
        package = json.loads(package_path.read_text(encoding="utf-8"))
        slot = str(package.get("editorial_slot", ""))
        number = slot.removeprefix("card_").lstrip("0") or "0"
        by_slug[str(package.get("article_slug", ""))] = manifest.get(number, {})
    projected = 0
    unresolved: list[str] = []
    for preview in pending:
        headline = preview.select_one("h2 a[href]")
        label = headline.get_text(" ", strip=True)
        slug = Path(str(headline.get("href", "")).split("?", 1)[0]).stem
        media = by_slug.get(slug, {})
        video = str(media.get("video_url", ""))
        image = str(media.get("hero_image_path", ""))
        copy = preview.select_one(".preview-copy")
        if copy is None or not (video or image):
            unresolved.append(slug or "<unknown>")
            continue
        if video:
            hero = soup.new_tag("div", attrs={"class": "hero video preview-media"})
            frame = soup.new_tag("iframe", src=video, title=f"Video: {label}")
            frame["loading"] = "lazy"
            frame["referrerpolicy"] = "strict-origin-when-cross-origin"
            frame["allow"] = "accelerometer; encrypted-media; gyroscope; picture-in-picture"
            frame["allowfullscreen"] = ""
            hero.append(frame)
        else:
            hero = soup.new_tag("div", attrs={"class": "hero preview-media"})
            tag = soup.new_tag("img", src=f"media/{Path(image).name}", alt=label)
            tag["loading"] = "lazy"
            hero.append(tag)
        copy.insert_before(hero)
        projected += 1
    if unresolved:
        raise ValueError(
            f"Issue {issue}: no approved media projected for preview(s) {', '.join(sorted(unresolved))}. "
            f"Projected {projected} of {len(pending)} preview(s); every hero-less preview must map to a "
            "manifest entry with video_url or hero_image_path."
        )
    return projected


def _replace_attr(soup: BeautifulSoup, selector: str, attr: str, old: str, new: str) -> None:
    for node in soup.select(selector):
        value = node.get(attr)
        if isinstance(value, str) and value.startswith(old):
            node[attr] = new + value[len(old):]


def _is_globally_routable(issue_dir: Path) -> bool:
    """Does this issue own publication-root article URLs?

    An article earns `/articles/<slug>/` by having an article package that names a real
    `article_slug`. Issues built before packages existed only have editorial slots (`card_01`),
    which are positions inside an edition rather than story identities, so they keep the
    issue-scoped routes they were published under. This replaces the previous rule, which granted
    the root routes to whichever issue happened to be newest and revoked them from every earlier
    issue on the next release.
    """
    package_dir = issue_dir / "article_packages"
    if not package_dir.is_dir():
        return False
    return any(
        str(json.loads(path.read_text(encoding="utf-8")).get("article_slug", "")).strip()
        for path in package_dir.glob("card_*.json")
    )


def _rewrite_issue_page(path: Path, issue: str, *, latest: bool, routable: bool = True) -> tuple[str, ...]:
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
    _set_issue_date(soup, issue)
    slugs: list[str] = []
    for link in soup.select('a[href^="articles/"]'):
        href = str(link.get("href", ""))
        slug = Path(href.split("?", 1)[0].split("#", 1)[0]).stem
        if slug and slug not in slugs:
            slugs.append(slug)
        if not routable:
            continue
        if latest:
            link["href"] = f"articles/{slug}/"
        else:
            link["href"] = f"../../articles/{slug}/"
    home = "index.html" if latest else "index.html"
    _replace_attr(soup, 'a[href^="newsletter.html"]', "href", "newsletter.html", home)
    search = "search/" if latest else "../../search/"
    _replace_attr(soup, 'a[href^="search.html"]', "href", "search.html", search.rstrip("/"))
    for form in soup.select('form[action="search.html"]'):
        form["action"] = search
    pagefind = "./pagefind/pagefind.js" if latest else "../../pagefind/pagefind.js"
    for node in soup.select("[data-pagefind-url]"):
        node["data-pagefind-url"] = pagefind
    if not latest:
        for link in soup.select("a[href]"):
            href = str(link["href"])
            for page in PUBLIC_PAGES:
                if href.startswith(page):
                    link["href"] = "../../" + href
    _write_soup(path, soup)
    return tuple(slugs)


def _rewrite_scoped_html(path: Path, issue: str, depth: int) -> None:
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
    prefix = "../" * depth
    _replace_attr(soup, 'a[href^="newsletter.html"]', "href", "newsletter.html", "index.html")
    for form in soup.select('form[action$="search.html"]'):
        form["action"] = prefix + "search/"
    for link in soup.select('a[href*="search.html"]'):
        value = str(link.get("href", ""))
        query = value.split("?", 1)[1] if "?" in value else ""
        link["href"] = prefix + "search/" + (f"?{query}" if query else "")
    for link in soup.select("a[href]"):
        value = str(link["href"])
        for page in PUBLIC_PAGES:
            if value.startswith("../" + page):
                link["href"] = prefix + value[3:]
            elif value.startswith(page):
                link["href"] = prefix + value
    for node in soup.select("[data-pagefind-url]"):
        node["data-pagefind-url"] = prefix + "pagefind/pagefind.js"
    _write_soup(path, soup)


def _rewrite_global_article(path: Path, issue: str, slugs: set[str]) -> None:
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
    for tag, attr in (("img", "src"), ("script", "src"), ("link", "href")):
        _replace_attr(soup, f'{tag}[{attr}^="../assets/"]', attr, "../assets/", f"../../issues/{issue}/assets/")
        _replace_attr(soup, f'{tag}[{attr}^="../media/"]', attr, "../media/", f"../../issues/{issue}/media/")
    for node in soup.select("[style]"):
        node["style"] = str(node["style"]).replace("../assets/", f"../../issues/{issue}/assets/")
    for link in soup.select("a[href]"):
        href = str(link["href"])
        bare, marker, suffix = href.partition("?")
        stem = Path(bare).stem
        if "/" not in bare and stem in slugs and bare.endswith(".html"):
            link["href"] = f"../{stem}/" + (f"?{suffix}" if marker else "")
        elif bare == "../newsletter.html":
            link["href"] = f"../../issues/{issue}/"
        elif bare == "../search.html":
            link["href"] = "../../search/" + (f"?{suffix}" if marker else "")
        else:
            for page in PUBLIC_PAGES:
                if href.startswith("../" + page):
                    link["href"] = "../../" + href[3:]
    for form in soup.select('form[action="../search.html"]'):
        form["action"] = "../../search/"
    for node in soup.select("[data-pagefind-url]"):
        node["data-pagefind-url"] = "../../pagefind/pagefind.js"
    _write_soup(path, soup)


@dataclass(frozen=True)
class HomeMedia:
    """One approved still that can stand in for a story on the front page."""

    src: str
    is_video: bool
    pictorial: bool


@dataclass(frozen=True)
class HomeStory:
    issue: str
    rank: int
    route: str
    headline: str
    lane: str
    dek: str
    media: HomeMedia | None

    @property
    def showable_media(self) -> HomeMedia | None:
        """Media the front page is willing to print, as opposed to media that merely exists."""
        return self.media if self.media is not None and self.media.pictorial else None


# How the publication names itself on its own front page. Every one of these is publication
# identity; none of them is any article's copy.
HOME_TITLE = "K-Signal · Signals from the Korean internet"
HOME_HEADING = "K-Signal — what the Korean internet is talking about"
HOME_STANDFIRST = "Signals from the Korean internet, read and explained."

# The issue page's own editorial classes are the ranking the pipeline already produces. The
# homepage reads that order rather than introducing a second ranking layer or a hand-maintained
# homepage-content file.
EDITORIAL_ORDER = ("lead", "secondary", "supporting")

# Issue membership is metadata, so being one edition newer is worth less than one editorial rank.
# At 0.75 the lead of the previous edition still outranks the third story of the current one,
# which is the whole point: the front page is a pool, not a stack of editions.
RECENCY_WEIGHT = 0.75

# Roles, adapted from the promo roles in BBC Simorgh's HierarchicalGrid. A role decides geometry
# and what the story suppresses; it is never a property of the story itself.
LEAD, FEATURE, VERTICAL, HORIZONTAL, COMPACT = "lead", "feature", "vertical", "horizontal", "compact"
MEDIA_ROLES = frozenset({LEAD, FEATURE, VERTICAL, HORIZONTAL})
DEK_ROLES = frozenset({LEAD, FEATURE, VERTICAL})
# Package 1 is the front; package 2 is a denser second collection. Both are editorial packages,
# neither is an edition.
# The front's fourth and fifth positions are the bottom of the right rail: without the trailing
# compact the rail stops short of the lead column and the package ends on a hole.
FRONT_ROLES = (LEAD, VERTICAL, VERTICAL, HORIZONTAL, COMPACT)
MORE_ROLES = (FEATURE, VERTICAL)

# A poster whose pixels are mostly near-white and almost unsaturated is a screenshot of a document
# — a text post, a chat capture, a chart — not an editorial photograph. Printed at card size it
# reads as a grey smudge, so those stories get the text-only treatment the reference gives its
# compact promos. Measured on the approved media itself rather than kept in a hand-maintained
# list: on this publication's current media the two document captures score 0.74/0.78 white with
# 0.005-0.018 saturation, and the six photographs score at most 0.053 white with 0.06 or more.
PICTORIAL_MAX_WHITE = 0.5
PICTORIAL_MIN_SATURATION = 0.05
# A cut-out is the second kind of non-photograph: an asset drawn to be composited onto something
# else — a club crest, a badge, a wordmark — rather than a picture of an event. Printed into a
# fixed picture box over the media placeholder it reads as a logo tile, which is branding, not
# reporting. Measured the same way as whiteness, on the approved media itself: on this
# publication's current media exactly one file carries transparency at all, and it is 0.52
# transparent; every photograph and every projected video poster is fully opaque.
PICTORIAL_MAX_TRANSPARENT = 0.05


def _is_cutout(handle: object) -> bool:
    """True when a meaningful share of the asset is transparent, i.e. it is a composited graphic."""
    if handle.mode not in {"RGBA", "LA", "PA"} and "transparency" not in handle.info:
        return False
    band = handle.convert("RGBA").getchannel("A")
    band.thumbnail((160, 160))
    alpha = list(band.getdata())
    if not alpha:
        return False
    return sum(1 for value in alpha if value < 250) / len(alpha) > PICTORIAL_MAX_TRANSPARENT


def _is_pictorial(path: Path) -> bool:
    try:
        from PIL import Image
    except ImportError:  # Pillow absent: print the approved media rather than silently dropping it
        return True
    try:
        with Image.open(path) as handle:
            if _is_cutout(handle):
                return False
            image = handle.convert("RGB")
            image.thumbnail((160, 160))
            pixels = list(image.getdata())
    except Exception:  # noqa: BLE001 - an unreadable poster is a media problem, not a layout one
        return True
    if not pixels:
        return True
    white = sum(1 for r, g, b in pixels if r > 235 and g > 235 and b > 235) / len(pixels)
    saturation = sum((max(p) - min(p)) / 255 for p in pixels) / len(pixels)
    return not (white > PICTORIAL_MAX_WHITE and saturation < PICTORIAL_MIN_SATURATION)


def _home_media_index(issue_dir: Path, issue: str) -> dict[str, HomeMedia]:
    """Map each story slug to the approved still the front page may print for it.

    Preference order, and no step invents anything: the approved local poster or thumbnail that
    the media pipeline already recorded for the story, then the hero image, then nothing. A
    video-backed story resolves to `video_thumbnail_path` — the official poster frame of the video
    the issue already holds embed rights to, acquired by `scripts/fetch_video_posters.py` — so the
    front page can show the story without shipping a player.
    """
    index: dict[str, HomeMedia] = {}
    manifest_path = issue_dir / "media" / "media_manifest.json"
    package_dir = issue_dir / "article_packages"
    if manifest_path.exists() and package_dir.is_dir():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for package_path in sorted(package_dir.glob("card_*.json")):
            package = json.loads(package_path.read_text(encoding="utf-8"))
            slug = str(package.get("article_slug", ""))
            number = str(package.get("editorial_slot", "")).removeprefix("card_").lstrip("0") or "0"
            entry = manifest.get(number, {})
            source = str(entry.get("video_thumbnail_path") or entry.get("hero_image_path") or "")
            if not slug or not source:
                continue
            local = issue_dir / "media" / Path(source).name
            index[slug] = HomeMedia(
                src=f"issues/{issue}/media/{Path(source).name}",
                is_video=bool(entry.get("video_url")),
                pictorial=_is_pictorial(local) if local.exists() else True,
            )
    return index


def _collect_home_stories(staged: Path, source_root: Path, issues: tuple[str, ...]) -> list[HomeStory]:
    """Read every published story from the assembled issue pages.

    The issue page previews are the canonical projection of each story: public headline, dek, lane
    label and the article's canonical route are all already resolved there by the time this runs.
    Reading them keeps the homepage and the article pages on one record per story instead of a
    duplicate homepage dataset. Media is the one thing not taken from the preview: an issue page
    may legitimately carry a player, and the front page may not, so the still is resolved from the
    same approved media records the preview was built from.
    """
    stories: list[HomeStory] = []
    for issue in issues:
        page = staged / "issues" / issue / "index.html"
        soup = BeautifulSoup(page.read_text(encoding="utf-8"), "html.parser")
        by_slug = _home_media_index(source_root / issue, issue)
        for preview in soup.select("article.story-preview"):
            headline = preview.select_one("h2 a[href]")
            if headline is None:
                continue
            classes = [str(name) for name in preview.get("class", [])]
            rank = min(
                (EDITORIAL_ORDER.index(name) for name in classes if name in EDITORIAL_ORDER),
                default=len(EDITORIAL_ORDER),
            )
            href = str(headline.get("href", ""))
            route = href[6:] if href.startswith("../../") else f"issues/{issue}/{href}"
            slug = Path(href.split("?", 1)[0].split("#", 1)[0]).stem
            media = by_slug.get(slug)
            if media is None:
                # An issue built before article packages existed keeps its media in the preview,
                # which is already a still, so it is re-anchored rather than re-resolved.
                baked = preview.select_one(".hero img[src]")
                if baked is not None:
                    src = str(baked.get("src", "")).lstrip("./")
                    local = source_root / issue / src
                    media = HomeMedia(
                        src=f"issues/{issue}/{src}",
                        is_video="video" in (preview.select_one(".hero").get("class") or []),
                        pictorial=_is_pictorial(local) if local.exists() else True,
                    )
            lane = preview.select_one(".topline em")
            # `.dek` specifically: the first paragraph in the preview is the issue kicker, which
            # is exactly the edition framing the homepage is meant to stop repeating per card.
            dek = preview.select_one(".preview-copy p.dek")
            stories.append(
                HomeStory(
                    issue=issue,
                    rank=rank,
                    route=route,
                    headline=headline.get_text(" ", strip=True),
                    lane=lane.get_text(" ", strip=True) if lane else "",
                    dek=dek.get_text(" ", strip=True) if dek else "",
                    media=media,
                )
            )
    if not stories:
        raise ValueError("No published story previews were found to build the homepage from")
    return stories


def _editorial_pool(stories: list[HomeStory]) -> list[HomeStory]:
    """Order every publishable story as one pool, then break runs of a single issue.

    Existing editorial rank is the signal; edition recency is a smaller one. The de-clumping pass
    is what stops the result being "this edition, then the last one" without inventing a ranking:
    it only ever swaps a story with an immediate neighbour of comparable standing.
    """
    editions = sorted({s.issue for s in stories}, key=lambda i: (_issue_date(i), i), reverse=True)
    ordered = sorted(
        enumerate(stories),
        key=lambda pair: (
            pair[1].rank + editions.index(pair[1].issue) * RECENCY_WEIGHT,
            editions.index(pair[1].issue),
            pair[0],
        ),
    )
    pool = [story for _, story in ordered]
    for index in range(1, len(pool)):
        if pool[index].issue != pool[index - 1].issue:
            continue
        for candidate in range(index + 1, min(index + 3, len(pool))):
            if pool[candidate].issue != pool[index - 1].issue:
                pool[index], pool[candidate] = pool[candidate], pool[index]
                break
    return pool


def _assign_roles(pool: list[HomeStory]) -> list[tuple[HomeStory, str]]:
    """Give each position a role, then re-seat stories so media roles get printable media.

    Position decides the role; the story only decides whether it can fill one. A story whose
    approved media is a document capture is moved out of a picture slot and swapped with the next
    story that can hold one, rather than being printed with a grey rectangle or being demoted out
    of the front page for a reason no reader would recognise.
    """
    roles = [
        *FRONT_ROLES[: len(pool)],
        *MORE_ROLES[: max(0, len(pool) - len(FRONT_ROLES))],
    ]
    roles += [COMPACT] * (len(pool) - len(roles))
    seated = list(pool)
    for index, role in enumerate(roles):
        if role not in MEDIA_ROLES or seated[index].showable_media is not None:
            continue
        swap = next(
            (
                other
                for other in range(index + 1, len(seated))
                if roles[other] not in MEDIA_ROLES and seated[other].showable_media is not None
            ),
            None,
        )
        if swap is not None:
            seated[index], seated[swap] = seated[swap], seated[index]
    return list(zip(seated, roles))


PLAY_GLYPH = (
    '<svg viewBox="0 0 44 44" width="44" height="44" focusable="false" aria-hidden="true">'
    '<circle cx="22" cy="22" r="21" fill="rgba(16,24,40,.62)" stroke="rgba(255,255,255,.85)" '
    'stroke-width="1.5"></circle><path d="M18 14l13 8-13 8z" fill="#fff"></path></svg>'
)
# Aspect ratio per role. The lead is the only story whose picture is allowed to be large, and even
# then 16:9 rather than the near-square crop that turned the old front page into one video frame.
ROLE_RATIO = {LEAD: "16/9", FEATURE: "16/9", VERTICAL: "16/9", HORIZONTAL: "1/1"}


def _home_card(soup: BeautifulSoup, story: HomeStory, role: str, *, slot: int) -> object:
    card = soup.new_tag("article", attrs={"class": "home-story"})
    card["data-role"] = role
    card["data-issue-id"] = story.issue
    card["data-route"] = story.route
    media = story.showable_media if role in MEDIA_ROLES else None
    if media is not None:
        # The picture is a second door onto the same story, so it carries the article's URL and is
        # hidden from assistive technology: the headline link beside it already says where it goes.
        frame = soup.new_tag("a", href=story.route, attrs={"class": "home-media"})
        frame["style"] = f"--ratio:{ROLE_RATIO.get(role, '16/9')}"
        frame["tabindex"] = "-1"
        frame["aria-hidden"] = "true"
        image = soup.new_tag("img", src=media.src, alt="")
        image["loading"] = "eager" if slot == 0 else "lazy"
        if slot == 0:
            image["fetchpriority"] = "high"
        frame.append(image)
        if media.is_video:
            play = soup.new_tag("span", attrs={"class": "home-play"})
            play.append(BeautifulSoup(PLAY_GLYPH, "html.parser"))
            frame.append(play)
        card.append(frame)
    block = soup.new_tag("div", attrs={"class": "home-copy"})
    if story.lane:
        lane = soup.new_tag("p", attrs={"class": "home-lane"})
        lane.string = story.lane
        block.append(lane)
    heading = soup.new_tag("h2" if role == LEAD else "h3", attrs={"class": "home-head"})
    link = soup.new_tag("a", href=story.route)
    link.string = story.headline
    heading.append(link)
    block.append(heading)
    if role in DEK_ROLES and story.dek:
        dek = soup.new_tag("p", attrs={"class": "home-dek"})
        dek.string = story.dek
        block.append(dek)
    card.append(block)
    return card


def _home_package(
    soup: BeautifulSoup, assigned: list[tuple[HomeStory, str]], *, offset: int, modifier: str
) -> object:
    """One editorial package: a grid of slots, with trailing headline-only rows grouped together.

    The front is the exception: its single trailing compact is the last item of the right rail,
    so it stays a slot on the package grid instead of being wrapped in a full-width row block.
    """
    package = soup.new_tag("div", attrs={"class": f"home-package home-package--{modifier}"})
    grouped = modifier != "front"
    rows = None
    for index, (story, role) in enumerate(assigned):
        slot = soup.new_tag("div")
        slot["data-slot"] = str(index)
        slot.append(_home_card(soup, story, role, slot=offset + index))
        if role == COMPACT and grouped:
            if rows is None:
                rows = soup.new_tag("div", attrs={"class": "home-rows"})
                package.append(rows)
            rows.append(slot)
        else:
            package.append(slot)
    return package


def site_date(clock: datetime | None = None) -> date:
    """The publication's current date, in the newsroom's own timezone.

    This is site context, not edition metadata: `/` states when the publication is being read, and
    `/issues/<id>/` states when that edition was published. `clock` is the injection seam, so a
    build or a test can pin the date without the module reading the wall clock.
    """
    moment = clock or datetime.now(ZoneInfo("America/New_York"))
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=ZoneInfo("America/New_York"))
    return moment.astimezone(ZoneInfo("America/New_York")).date()


def _project_home_page(
    staged: Path, source_root: Path, issues: tuple[str, ...], *, clock: datetime | None = None
) -> int:
    """Replace the homepage body with a publication front page.

    The staged `index.html` arrives as a copy of the latest issue's newsletter, which is why `/`
    and `/issues/<latest>/` were previously the same document. The shell — header, footer, styles,
    search wiring — is kept; only `<main>` is rebuilt, so the homepage stops being an edition and
    becomes a view over every publishable story. Nothing on the page is grouped by issue.
    """
    path = staged / "index.html"
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
    stories = _collect_home_stories(staged, source_root, issues)
    assigned = _assign_roles(_editorial_pool(stories))

    old_main = soup.select_one("main")
    aliases = soup.select_one(".search-aliases")
    main = soup.new_tag("main", attrs={"class": "home-shell"})

    # The document title arrives from the newsletter this file was copied from, which carried an
    # article's interpretive section heading. That heading is article body copy: it must not name
    # the front page in the tab, in a bookmark, or in anything generated from the document title.
    if soup.title is not None:
        soup.title.string = HOME_TITLE
    elif soup.head is not None:
        heading = soup.new_tag("title")
        heading.string = HOME_TITLE
        soup.head.append(heading)
    for meta in soup.select('meta[name="description"], meta[property="og:title"], meta[property="og:description"]'):
        meta["content"] = HOME_TITLE if meta.get("property") == "og:title" else HOME_STANDFIRST

    masthead = soup.new_tag("header", attrs={"class": "home-masthead"})
    # The publication names itself here, and only here. The h1 is visually hidden because the
    # masthead logo already carries the identity on screen, and because an article's own words are
    # not the front page's headline.
    title = soup.new_tag("h1", attrs={"class": "home-vh"})
    title.string = HOME_HEADING
    masthead.append(title)
    standfirst = soup.new_tag("p", attrs={"class": "home-standfirst"})
    standfirst.string = HOME_STANDFIRST
    masthead.append(standfirst)
    today = site_date(clock)
    stamp = soup.new_tag("p", attrs={"class": "home-datestamp"})
    published = soup.new_tag("time", datetime=today.isoformat())
    published.string = f"{today.strftime('%A, %B')} {today.day}, {today.year}"
    stamp.append(published)
    masthead.append(stamp)
    main.append(masthead)

    front = soup.new_tag("section", attrs={"class": "home-front", "aria-label": "Front"})
    front.append(_home_package(soup, assigned[: len(FRONT_ROLES)], offset=0, modifier="front"))
    main.append(front)

    if assigned[len(FRONT_ROLES):]:
        more = soup.new_tag("section", attrs={"class": "home-more", "aria-label": "More signals"})
        head = soup.new_tag("div", attrs={"class": "home-pkg-head"})
        label = soup.new_tag("h2", attrs={"class": "home-pkg-label"})
        label.string = "More signals"
        head.append(label)
        more.append(head)
        more.append(
            _home_package(
                soup, assigned[len(FRONT_ROLES):], offset=len(FRONT_ROLES), modifier="more"
            )
        )
        main.append(more)

    if aliases is not None:
        main.append(aliases.extract())
    if old_main is not None:
        old_main.replace_with(main)
    else:
        soup.body.append(main)
    _write_soup(path, soup)
    return len(stories)


def _archive_from_shell(home_path: Path, issues: tuple[str, ...]) -> BeautifulSoup:
    soup = BeautifulSoup(home_path.read_text(encoding="utf-8"), "html.parser")
    old_main = soup.select_one("main")
    main = soup.new_tag("main", attrs={"class": "policy-shell archive-shell", "data-pagefind-body": ""})
    back = soup.new_tag("a", href="../", attrs={"class": "article-back"}); back.string = "← K-Signal home"; main.append(back)
    header = soup.new_tag("header"); kicker = soup.new_tag("p", attrs={"class": "policy-kicker"}); kicker.string = "K-Signal publication"; header.append(kicker)
    title = soup.new_tag("h1"); title.string = "Archive"; header.append(title); main.append(header)
    listing = soup.new_tag("ol", attrs={"class": "archive-list"})
    for issue in reversed(issues):
        published = _issue_date(issue)
        item = soup.new_tag("li"); link = soup.new_tag("a", href=f"../issues/{issue}/")
        strong = soup.new_tag("strong"); strong.string = f"Issue {issue}"; link.append(strong)
        date_node = soup.new_tag("time", datetime=published); date_node.string = published; link.append(date_node)
        item.append(link); listing.append(item)
    main.append(listing)
    if old_main: old_main.replace_with(main)
    for selector, attribute in (("a[href]", "href"), ("img[src]", "src"), ("script[src]", "src"), ("form[action]", "action")):
        for node in soup.select(selector):
            value = str(node.get(attribute, ""))
            if value and not value.startswith(("../", "#", "http:", "https:", "mailto:", "tel:", "data:")):
                node[attribute] = "../" + value.removeprefix("./")
    for node in soup.select("[data-pagefind-url]"):
        node["data-pagefind-url"] = "../pagefind/pagefind.js"
    for node in soup.select("[style]"):
        node["style"] = str(node["style"]).replace("url('assets/", "url('../assets/")
    return soup


def _project_interaction_scripts(staged: Path) -> tuple[str, ...]:
    """Patch every staged assets/ksignal.js, not only the root copy.

    Issue-scoped pages and article pages load their own copy of the script, so patching one copy
    leaves lane interaction broken on those routes while the injected CSS still makes them look
    correct. A missing source marker means issue_builder's script drifted: fail rather than write
    an unchanged file that silently ships the original defect.
    """
    patched: list[str] = []
    for script in sorted(staged.rglob("assets/ksignal.js")):
        route = script.relative_to(staged).as_posix()
        text = script.read_text(encoding="utf-8")
        missing_source = [marker for marker in (INTERACTION_SOURCE, POPOVER_SOURCE) if marker not in text]
        if missing_source:
            raise ValueError(
                f"{route} does not contain the expected lane interaction source {missing_source}. "
                "The site interaction projection is out of date with issue_builder output."
            )
        text = text.replace(INTERACTION_SOURCE, INTERACTION_TARGET)
        text = text.replace(POPOVER_SOURCE, POPOVER_TARGET)
        text = text.rstrip() + POPOVER_RESIZE_RESET
        missing_markers = [marker for marker in INTERACTION_MARKERS if marker not in text]
        if missing_markers:
            raise ValueError(f"{route} is missing interaction markers after projection: {missing_markers}")
        script.write_text(text, encoding="utf-8")
        patched.append(route)
    if not patched:
        raise FileNotFoundError("No staged assets/ksignal.js was found to receive the interaction projection")
    return tuple(patched)


def _project_header(soup: BeautifulSoup, route: str) -> None:
    """Restructure the masthead into a primary row and a lane row.

    The header markup comes from issue_builder, which emits logo and search side by side with the
    lanes pushed to the right of the same row. The layout wanted here is logo / Subscribe / Search
    on one row and a page-centred lane row beneath, which the stylesheet can only express once the
    right-hand controls share a wrapper and the lane nav is a sibling of that row. Nothing is
    rebuilt: `.site-search` is moved intact, so its Pagefind wiring and every selector
    `assets/ksignal.js` and the QA tools depend on survive unchanged.
    """
    header = soup.select_one("header.site-header")
    if header is None:
        return
    nodes = {
        ".header-main": header.select_one(".header-main"),
        "a.brand": header.select_one("a.brand"),
        ".site-search": header.select_one(".site-search"),
        "nav.lane-nav": header.select_one("nav.lane-nav"),
    }
    missing = [selector for selector, node in nodes.items() if node is None]
    if missing:
        raise ValueError(
            f"{route}: header.site-header is missing {missing}. The masthead projection is out of "
            "date with issue_builder output."
        )
    if header.select_one(".header-actions") is not None:
        return
    actions = soup.new_tag("div", attrs={"class": "header-actions"})
    # Presentation only. A repo-wide search found no newsletter, mailing-list, or email-signup
    # mechanism to wire this to, so it must not navigate anywhere or claim to be operable.
    subscribe = soup.new_tag(
        "button",
        type="button",
        attrs={"class": "subscribe-control", "aria-disabled": "true", "data-subscribe-state": "presentation"},
    )
    subscribe.string = "Subscribe"
    actions.append(subscribe)
    actions.append(nodes[".site-search"].extract())
    nodes[".header-main"].append(actions)
    header.append(nodes["nav.lane-nav"].extract())


def _project_internet_read(soup: BeautifulSoup) -> int:
    """Mark the in-article interpretive section so the stylesheet can reach it.

    Adding a class is the whole DOM change: the heading and body text are editorial copy and are
    left exactly as written.
    """
    marked = 0
    for section in soup.select(".article-body section"):
        heading = section.find("h2")
        if heading is None:
            continue
        if " ".join(heading.get_text(" ", strip=True).split()).casefold() != INTERNET_READ_HEADING:
            continue
        classes = list(section.get("class", []))
        if "internet-read" not in classes:
            section["class"] = [*classes, "internet-read"]
        marked += 1
    return marked


ISSUE_ROUTE = re.compile(r"^issues/(\d+)/index\.html$")


def _project_edition_context(soup: BeautifulSoup, route: str) -> bool:
    """Say, on an issue page, that this is an archived edition — and how to get back to the front.

    Without it `/issues/<id>/` reads as a second homepage and the logo is the only way out, so a
    reader who arrives from a story's "More from this issue" has no stated route to the current
    publication. The link is explicit rather than relying on the masthead.
    """
    match = ISSUE_ROUTE.match(route)
    main = soup.select_one("main")
    if match is None or main is None or main.select_one(".edition-bar") is not None:
        return False
    bar = soup.new_tag("nav", attrs={"class": "edition-bar", "aria-label": "Edition"})
    back = soup.new_tag("a", href="../../", attrs={"class": "edition-home", "data-site-home": ""})
    back.string = "← Latest from K-Signal"
    bar.append(back)
    note = soup.new_tag("p", attrs={"class": "edition-note"})
    note.append(soup.new_string(f"Archived edition · Issue {match.group(1)} · "))
    archive = soup.new_tag("a", href="../../archive/")
    archive.string = "All editions"
    note.append(archive)
    bar.append(note)
    main.insert(0, bar)
    return True


ARTICLE_ROUTE = re.compile(r"^(articles/[^/]+/index\.html|issues/\d+/articles/[^/]+\.html)$")


def _canonical_route(route: str) -> str:
    """The one public path that owns this document.

    Directory-indexed routes canonicalise to their directory so `/articles/<slug>/index.html` and
    `/articles/<slug>/` cannot be indexed or linked as two different stories.
    """
    if route == "index.html":
        return "/"
    if route.endswith("/index.html"):
        return "/" + route[: -len("index.html")]
    return "/" + route


def _project_discovery(soup: BeautifulSoup, route: str, base: str) -> bool:
    """Declare the canonical URL and keep the search index editorial.

    Every document states the path it owns, so homepage placement, lane filtering, and archive
    listings can never imply a second address for one story. Pagefind then indexes article
    documents only: `/`, the issue pages, `/archive/`, and `/search/` are discovery surfaces that
    point at articles, and indexing them made the front page and the archive compete with the
    stories they exist to route to.
    """
    canonical = _canonical_route(route)
    head = soup.head
    if head is not None and base:
        for existing in head.select('link[rel="canonical"]'):
            existing.decompose()
        head.append(soup.new_tag("link", rel="canonical", href=base.rstrip("/") + canonical))
    article = bool(ARTICLE_ROUTE.match(route))
    if article:
        shell = soup.select_one("main.article-shell")
        if shell is not None:
            # The published route, not the pre-assembly filename the issue builder recorded.
            shell["data-route"] = canonical.lstrip("/")
        return True
    for node in soup.select("[data-pagefind-body]"):
        del node["data-pagefind-body"]
    if soup.body is not None:
        soup.body["data-pagefind-ignore"] = ""
    return False


def _project_site_assets(staged: Path, *, base_url: str = "") -> tuple[str, ...]:
    patched = _project_interaction_scripts(staged)
    indexed: list[str] = []
    for path in sorted(staged.rglob("*.html")):
        soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
        if soup.head is None and soup.html is not None:
            # A document with no head still owns a URL and needs the site stylesheet, so it gets a
            # head rather than silently shipping unstyled and uncanonicalised.
            soup.html.insert(0, soup.new_tag("head"))
        style = soup.new_tag("style", attrs={"data-persistent-site-responsive": ""}); style.string = SITE_RESPONSIVE_CSS
        if soup.head: soup.head.append(style)
        route = path.relative_to(staged).as_posix()
        if _project_discovery(soup, route, base_url):
            indexed.append(route)
        _project_header(soup, route)
        _project_internet_read(soup)
        _project_edition_context(soup, route)
        presentation = soup.new_tag("style", attrs={"data-persistent-site-presentation": ""})
        presentation.string = SITE_PRESENTATION_CSS + HOME_TOKENS_CSS + HOME_CSS
        if soup.head: soup.head.append(presentation)
        relative = path.relative_to(staged)
        depth = len(relative.parent.parts)
        root = "../" * depth or "./"
        brand = soup.select_one("a.brand")
        if brand: brand["href"] = root
        footer_nav = soup.select_one("footer.site-footer nav")
        if footer_nav and not footer_nav.select_one("a[data-site-archive]"):
            archive = soup.new_tag("a", href=root + "archive/", attrs={"data-site-archive": ""}); archive.string = "Archive"; footer_nav.append(archive)
        _write_soup(path, soup)
    return patched


def assemble_site(
    issues: tuple[str, ...] = ("001", "002"),
    *,
    issues_root: str | Path = "outputs/issues",
    site_dir: str | Path = "outputs/site",
    run_pagefind: bool = True,
    clock: datetime | None = None,
) -> SiteBuild:
    if not issues:
        raise ValueError("At least one issue is required")
    source_root = Path(issues_root).resolve()
    destination = Path(site_dir)
    latest = issues[-1]
    for issue in issues:
        source = source_root / issue
        if not (source / "newsletter.html").is_file():
            raise FileNotFoundError(f"Issue {issue} is missing newsletter.html")
    for issue in issues:
        _issue_date(issue)

    with tempfile.TemporaryDirectory(prefix="ksignal-site-") as temp_name:
        staged = Path(temp_name) / "site"
        staged.mkdir()
        latest_dir = source_root / latest
        shutil.copy2(latest_dir / "newsletter.html", staged / "index.html")
        root_soup = BeautifulSoup((staged / "index.html").read_text(encoding="utf-8"), "html.parser")
        root_projected = _project_preview_media(root_soup, latest_dir, latest)
        _write_soup(staged / "index.html", root_soup)
        latest_slugs = _rewrite_issue_page(staged / "index.html", latest, latest=True)
        for name in PUBLIC_PAGES:
            shutil.copy2(latest_dir / name, staged / name)
        if (latest_dir / "search.html").exists():
            shutil.copy2(latest_dir / "search.html", staged / "search.html")
        for dirname in PUBLIC_DIRS:
            shutil.copytree(latest_dir / dirname, staged / dirname)

        routable = {issue: _is_globally_routable(source_root / issue) for issue in issues}
        issue_slugs: dict[str, tuple[str, ...]] = {}
        for issue in issues:
            source = source_root / issue
            scoped = staged / "issues" / issue
            scoped.mkdir(parents=True)
            shutil.copy2(source / "newsletter.html", scoped / "index.html")
            if issue == latest:
                scoped_soup = BeautifulSoup((scoped / "index.html").read_text(encoding="utf-8"), "html.parser")
                scoped_projected = _project_preview_media(scoped_soup, source, issue)
                if scoped_projected != root_projected:
                    raise ValueError(
                        f"Issue {issue}: root projected {root_projected} preview(s) but the permanent "
                        f"issue page projected {scoped_projected}"
                    )
                _write_soup(scoped / "index.html", scoped_soup)
            issue_slugs[issue] = _rewrite_issue_page(
                scoped / "index.html", issue, latest=False, routable=routable[issue]
            )
            for dirname in PUBLIC_DIRS:
                shutil.copytree(source / dirname, scoped / dirname)
            if not routable[issue]:
                shutil.copytree(source / "articles", scoped / "articles")
                for article in (scoped / "articles").glob("*.html"):
                    html = article.read_text(encoding="utf-8").replace("../newsletter.html", "../index.html")
                    article.write_text(html, encoding="utf-8")
                    _rewrite_scoped_html(article, issue, 3)

        # Publication-root article routes. Every routable issue keeps its slugs permanently, so a
        # new release adds routes instead of revoking the previous issue's.
        owner: dict[str, str] = {}
        published_slugs: list[str] = []
        for issue in issues:
            if not routable[issue]:
                continue
            slug_set = set(issue_slugs[issue])
            for slug in issue_slugs[issue]:
                if slug in owner:
                    raise ValueError(
                        f"Article slug {slug!r} is claimed by both issue {owner[slug]} and issue {issue}. "
                        "Publication-root article URLs require globally unique slugs; rename one before "
                        "assembling the site."
                    )
                owner[slug] = issue
                source = source_root / issue / "articles" / f"{slug}.html"
                if not source.exists():
                    raise FileNotFoundError(f"Readable article source is missing: {source}")
                target = staged / "articles" / slug / "index.html"
                target.parent.mkdir(parents=True)
                shutil.copy2(source, target)
                _rewrite_global_article(target, issue, slug_set)
                published_slugs.append(slug)

        home_story_count = _project_home_page(staged, source_root, issues, clock=clock)

        archive = staged / "archive" / "index.html"
        archive.parent.mkdir()
        _write_soup(archive, _archive_from_shell(staged / "index.html", issues))

        search_dir = staged / "search"
        search_dir.mkdir(exist_ok=True)
        if (staged / "search.html").exists():
            shutil.move(staged / "search.html", search_dir / "index.html")
            soup = BeautifulSoup((search_dir / "index.html").read_text(encoding="utf-8"), "html.parser")
            _replace_attr(soup, 'a[href="newsletter.html"]', "href", "newsletter.html", "../")
            _replace_attr(soup, 'a[href^="assets/"]', "href", "assets/", "../assets/")
            _replace_attr(soup, 'img[src^="assets/"]', "src", "assets/", "../assets/")
            _replace_attr(soup, 'script[src^="assets/"]', "src", "assets/", "../assets/")
            for node in soup.select("[data-pagefind-url]"):
                node["data-pagefind-url"] = "../pagefind/pagefind.js"
            for form in soup.select('form[action="search.html"]'):
                form["action"] = "./"
            for node in soup.select("[style]"):
                node["style"] = str(node["style"]).replace("url('assets/", "url('../assets/")
            for script in soup.select('script[type="module"]'):
                script.string = (script.string or "").replace("'./pagefind/pagefind.js'", "'../pagefind/pagefind.js'")
            for link in soup.select('a[href^="search.html"]'):
                value = str(link["href"])
                link["href"] = "./" + ("?" + value.split("?", 1)[1] if "?" in value else "")
            for link in soup.select("a[href]"):
                value = str(link["href"])
                for page in PUBLIC_PAGES:
                    if value.startswith(page):
                        link["href"] = "../" + value
            _write_soup(search_dir / "index.html", soup)

        for name in PUBLIC_PAGES:
            _rewrite_scoped_html(staged / name, latest, 0)
        _project_site_assets(staged, base_url=os.environ.get("SITE_BASE_URL", DEFAULT_SITE_BASE_URL))
        (staged / "_headers").write_text(NETLIFY_HEADERS, encoding="utf-8")

        pagefind_count = 0
        if run_pagefind:
            executable = Path("node_modules/.bin/pagefind.cmd")
            if not executable.exists():
                raise FileNotFoundError("Pagefind is not installed. Run npm install first.")
            result = subprocess.run(
                [str(executable.resolve()), "--site", str(staged.resolve()), "--output-subdir", "pagefind", "--force-language", "ko"],
                check=True, capture_output=True, text=True,
            )
            pagefind_count = _pagefind_page_count(result.stdout)

        errors = validate_host_package(staged)
        if errors:
            raise ValueError("Persistent site validation failed:\n- " + "\n- ".join(errors))
        if destination.exists():
            _remove_tree(destination)
        shutil.copytree(staged, destination)

    return SiteBuild(
        site_dir=destination,
        issue_routes=tuple(f"/issues/{issue}/" for issue in issues),
        article_routes=tuple(f"/articles/{slug}/" for slug in published_slugs),
        pagefind_entry_count=pagefind_count,
    )
