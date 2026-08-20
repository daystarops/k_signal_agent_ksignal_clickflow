import json
from collections.abc import Iterator
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from contextlib import ExitStack, contextmanager
from pathlib import Path

import pytest
from bs4 import BeautifulSoup
from PIL import Image

from core.host_packager import validate_host_package
from core.site_assembler import (
    FRONT_ROLES,
    ISSUE_METADATA,
    PUBLIC_PAGES,
    _pagefind_page_count,
    assemble_site,
    site_date,
)


@contextmanager
def _registered_issue(issue: str, published: str) -> Iterator[None]:
    """Give a fixture issue a publication date without editing the shipped metadata."""
    ISSUE_METADATA[issue] = {"date": published}
    try:
        yield
    finally:
        ISSUE_METADATA.pop(issue, None)

def _write_swatch(path: Path, colour: tuple[int, int, int], size: tuple[int, int] = (64, 36)) -> None:
    """A real image, because the assembler now measures approved media rather than trusting it.

    A flat near-white swatch stands in for a document capture (a screenshot of a text post, a
    chart); anything else stands in for an editorial photograph.
    """
    Image.new("RGB", size, colour).save(path)


ISSUE_001_SLUGS = ("card-one", "card-two", "card-three", "card-four")
ISSUE_002_SLUGS = ("readable-one", "readable-two", "readable-three", "readable-four")


def _soup(path: Path) -> BeautifulSoup:
    return BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")


def _issue(root: Path, issue: str, slugs: tuple[str, ...], *, baked_media: bool = False) -> None:
    """Build a fixture issue.

    ``baked_media`` mirrors Issue 001, whose previews already carry image heroes and which has no
    ``article_packages``/manifest. Without it the previews arrive hero-less, mirroring Issue 002,
    which relies on the assembler projecting its already-approved selected media.
    """
    issue_dir = root / issue
    for dirname in ("articles", "assets", "media"):
        (issue_dir / dirname).mkdir(parents=True, exist_ok=True)
    (issue_dir / "assets" / "ksignal.css").write_text("body{}", encoding="utf-8")
    (issue_dir / "assets" / "ksignal.js").write_text(
        "const mobile=()=>matchMedia('(max-width:760px)').matches;"
        "n.classList.remove('is-open');"
        "n.querySelector('.lane-trigger')?.setAttribute('aria-expanded','false');"
        "if(!e.target.closest('.lane-item'))closeLanes();"
        "item.classList.add('is-open');button.setAttribute('aria-expanded','true')",
        encoding="utf-8",
    )
    (issue_dir / "assets" / "logo.png").write_bytes(b"png")
    _write_swatch(issue_dir / "media" / "hero.jpg", (40, 120, 60))
    hero = '<div class="hero"><img src="media/hero.jpg" alt="baked"></div>' if baked_media else ""
    lanes_by_slot = ("Fandom / 팬덤", "Sports / 스포츠", "Society / 사회", "Sports / 스포츠")
    links = "".join(
        f'<article class="story-preview {"lead" if index == 0 else "supporting"}">{hero}'
        f'<div class="preview-copy"><p class="issue-kicker">From Issue {issue}</p>'
        f'<div class="topline"><em>{lanes_by_slot[index % len(lanes_by_slot)]}</em></div>'
        f'<h2><a href="articles/{slug}.html">{slug}</a></h2>'
        f'<p class="dek">Why {slug} is worth reading.</p>'
        f'<a class="read-signal" href="articles/{slug}.html">Read</a></div></article>'
        for index, slug in enumerate(slugs)
    )
    # Every fixture issue carries the wrong baked date so the metadata correction is exercised.
    masthead = '<div class="issue-date"><time datetime="2026-01-01">Thursday, January 1, 2026</time></div>'
    # The masthead mirrors issue_builder's real structure. A logo-only stub cannot exercise the
    # header projection, and the projection is what the published layout depends on.
    lanes = "".join(
        f'<div class="lane-item" data-lane="{lane.lower()}">'
        f'<button class="lane-trigger" type="button" aria-expanded="false">{lane}</button>'
        f'<div class="lane-popover" role="menu"><a href="search.html?lane={lane}">View {lane}</a></div>'
        "</div>"
        for lane in ("Beauty", "Society", "Fandom", "Sports", "Food")
    )
    header = (
        '<header class="site-header"><div class="header-main">'
        '<a class="brand" href="newsletter.html"><img src="assets/logo.png"></a>'
        '<div class="site-search" data-pagefind-url="./pagefind/pagefind.js">'
        '<button class="search-toggle" type="button" aria-expanded="false"></button>'
        '<form class="search-form" action="search.html" role="search"><input name="q" type="search"></form>'
        '<div class="search-typeahead" hidden></div></div></div>'
        f'<nav class="lane-nav" aria-label="K-Signal lanes">{lanes}</nav></header>'
    )
    footer = '<footer class="site-footer"><nav></nav></footer><script src="assets/ksignal.js"></script>'
    common = header + footer + '<a href="search.html">search</a>'
    # The real newsletter titles itself with an article's interpretive section heading, and the
    # homepage is copied from this file, so the fixture has to carry the same leak to be able to
    # prove it is corrected.
    head = (
        "<head><title>K-Signal · What the Internet Is Really Saying</title>"
        '<meta content="What the Internet Is Really Saying" name="description">'
        '<meta content="What the Internet Is Really Saying" property="og:title"></head>'
    )
    (issue_dir / "newsletter.html").write_text(
        f'<html>{head}<body data-pagefind-body>{header}<main>{masthead}'
        f'<section class="front-page">{links}</section></main>{footer}</body></html>',
        encoding="utf-8",
    )
    (issue_dir / "search.html").write_text(
        f'<html><body>{common}<div data-pagefind-url="./pagefind/pagefind.js"></div></body></html>',
        encoding="utf-8",
    )
    for page in PUBLIC_PAGES:
        (issue_dir / page).write_text(f"<html><body>{common}</body></html>", encoding="utf-8")
    for slug in slugs:
        related = "".join(f'<a href="{other}.html">{other}</a>' for other in slugs if other != slug)
        body = (
            '<div class="article-body">'
            '<section class="translation"><h2>Korean</h2><p>원문</p></section>'
            "<section><h2>What the Internet Is Really Saying</h2>"
            f"<p>The interpretive read for {slug}.</p></section></div>"
        )
        (issue_dir / "articles" / f"{slug}.html").write_text(
            '<html><body data-pagefind-body><a href="../newsletter.html">issue</a>'
            '<a href="../search.html">search</a><img src="../media/hero.jpg">'
            f"{body}<script src=\"../assets/ksignal.js\"></script>{related}</body></html>",
            encoding="utf-8",
        )
    if baked_media:
        return
    packages = issue_dir / "article_packages"
    packages.mkdir()
    manifest = {}
    for index, slug in enumerate(slugs, 1):
        (packages / f"card_{index:02d}.json").write_text(
            json.dumps({"editorial_slot": f"card_{index:02d}", "article_slug": slug}), encoding="utf-8"
        )
        poster = issue_dir / "media" / f"card_{index:02d}_poster.jpg"
        # Card 2 gets a flat near-white swatch: a document capture, not a photograph.
        _write_swatch(poster, (250, 250, 250) if index == 2 else (30, 90, 160))
        manifest[str(index)] = {
            "video_url": f"https://www.youtube.com/embed/video{index}",
            "video_thumbnail_path": poster.as_posix(),
            "rights_status": "embed_only",
            "hero_credit": f"Rights holder {index}",
            "media_reason": f"Internal editorial rationale {index} that must never reach the page.",
        }
    (issue_dir / "media" / "media_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def _build(tmp_path: Path) -> Path:
    issues = tmp_path / "issues"
    _issue(issues, "001", ISSUE_001_SLUGS, baked_media=True)
    _issue(issues, "002", ISSUE_002_SLUGS)
    site = tmp_path / "site"
    assemble_site(("001", "002"), issues_root=issues, site_dir=site, run_pagefind=False)
    return site


def test_assembles_persistent_routes_without_mutating_issues(tmp_path: Path) -> None:
    issues = tmp_path / "issues"
    _issue(issues, "001", ISSUE_001_SLUGS, baked_media=True)
    _issue(issues, "002", ISSUE_002_SLUGS)
    before = (issues / "002" / "newsletter.html").read_bytes()
    site = tmp_path / "site"

    result = assemble_site(("001", "002"), issues_root=issues, site_dir=site, run_pagefind=False)

    assert result.issue_routes == ("/issues/001/", "/issues/002/")
    assert result.article_routes == tuple(f"/articles/{slug}/" for slug in ISSUE_002_SLUGS)
    assert (site / "index.html").exists()
    assert (site / "issues/001/articles/card-one.html").exists()
    assert (site / "issues/002/index.html").exists()
    assert (site / "articles/readable-one/index.html").exists()
    assert (site / "archive/index.html").exists()
    assert (site / "search/index.html").exists()
    assert (issues / "002" / "newsletter.html").read_bytes() == before
    assert (issues / "001" / "newsletter.html").read_bytes() != b""
    assert validate_host_package(site) == []

    homepage = _soup(site / "index.html")
    assert homepage.select_one('a[href="articles/readable-one/"]')
    article = _soup(site / "articles/readable-one/index.html")
    assert article.select_one('a[href="../../issues/002/"]')
    assert article.select_one('img[src="../../issues/002/media/hero.jpg"]')


def test_every_staged_interaction_script_is_projected(tmp_path: Path) -> None:
    """A: the root copy is not the only one. Scoped issue pages and article pages load their own."""
    site = _build(tmp_path)

    scripts = sorted(path.relative_to(site).as_posix() for path in site.rglob("assets/ksignal.js"))
    assert scripts == [
        "assets/ksignal.js",
        "issues/001/assets/ksignal.js",
        "issues/002/assets/ksignal.js",
    ]
    for route in scripts:
        text = (site / route).read_text(encoding="utf-8")
        assert "matchMedia('(hover:none), (pointer:coarse)')" in text, route
        assert "button.getBoundingClientRect().bottom+6" in text, route
        assert "document.body.appendChild(popover)" in text, route
        assert "closest('.lane-item,.lane-popover')" in text, route
        assert "matchMedia('(max-width:760px)').matches,delay" not in text, route


def test_phone_popover_offset_is_cleared_above_the_phone_breakpoint(tmp_path: Path) -> None:
    """An inline top measured at 390px must not survive a rotation into tablet widths."""
    site = _build(tmp_path)

    for path in site.rglob("assets/ksignal.js"):
        text = path.read_text(encoding="utf-8")
        route = path.relative_to(site).as_posix()
        # open handler clears the offset instead of only setting it
        assert "`${Math.ceil(button.getBoundingClientRect().bottom+6)}px`:''" in text, route
        # a popover left open across a rotation is reset without reopening
        assert "addEventListener('resize'" in text, route
        assert "document.querySelectorAll('.lane-popover').forEach(p=>{" in text, route
        assert "p.classList.remove('is-lifted');p.style.top=''" in text, route


def test_stale_interaction_source_fails_loudly(tmp_path: Path) -> None:
    issues = tmp_path / "issues"
    _issue(issues, "001", ISSUE_001_SLUGS, baked_media=True)
    _issue(issues, "002", ISSUE_002_SLUGS)
    (issues / "002" / "assets" / "ksignal.js").write_text("const mobile=()=>false;", encoding="utf-8")

    with pytest.raises(ValueError) as exc:
        assemble_site(("001", "002"), issues_root=issues, site_dir=tmp_path / "site", run_pagefind=False)
    assert "lane interaction source" in str(exc.value)


def test_homepage_previews_video_stories_with_a_poster_and_never_a_player(tmp_path: Path) -> None:
    """No player chrome on `/`. The issue route keeps its embed; the front page shows a still.

    The previous contract required four YouTube iframes on the homepage, which is what made the
    first viewport a single video frame. A video-backed story is now represented by the official
    poster the media pipeline already holds, plus a play affordance.
    """
    site = _build(tmp_path)
    home = _soup(site / "index.html")

    assert home.select("main iframe") == [], "the front page must ship no embedded player"
    assert "youtube.com/embed" not in (site / "index.html").read_text(encoding="utf-8")

    posters = home.select(".home-story .home-media img")
    assert posters, "video-backed stories still carry a still image"
    for poster in posters:
        src = str(poster.get("src"))
        assert src.startswith("issues/"), src
        assert (site / src).exists(), src

    played = home.select(".home-story .home-media .home-play svg")
    assert played, "a video-backed story is marked as video without embedding one"

    # The archived edition is unchanged: it is allowed to carry the player it published with.
    issue = _soup(site / "issues/002/index.html")
    assert len(issue.select(".story-preview .hero.video.preview-media iframe")) == 4


def test_homepage_media_and_headline_lead_to_the_same_canonical_article(tmp_path: Path) -> None:
    site = _build(tmp_path)

    stories = _soup(site / "index.html").select("article.home-story")
    assert len(stories) == 8
    for story in stories:
        headline = story.select_one(".home-head a[href]")
        assert headline is not None
        route = str(headline.get("href"))
        assert route == story.get("data-route")
        media = story.select_one("a.home-media")
        if media is not None:
            assert str(media.get("href")) == route, "the picture is a second door onto one story"
            # It duplicates the headline link, so it must not be a second stop for a screen reader.
            assert media.get("aria-hidden") == "true"
            assert media.get("tabindex") == "-1"


def test_homepage_omits_media_that_is_a_document_capture(tmp_path: Path) -> None:
    """Media strength is measured, so a screenshot of a text post never becomes a picture card.

    Card 2's approved poster is a flat near-white swatch. It must not be printed, and it must not
    occupy a picture slot either: the slot is re-seated onto a story that can fill it.
    """
    site = _build(tmp_path)
    home = _soup(site / "index.html")

    printed = {Path(str(img.get("src"))).name for img in home.select(".home-media img")}
    assert "card_02_poster.jpg" not in printed, "a document capture must not be printed"
    assert "card_01_poster.jpg" in printed

    quiet = home.select_one('article.home-story[data-route="articles/readable-two/"]')
    assert quiet is not None, "the story is still on the front page"
    assert quiet.select_one(".home-media") is None
    assert quiet.get("data-role") == "compact"
    # every story that did keep a picture slot actually has a picture in it
    for story in home.select("article.home-story"):
        if story.get("data-role") in {"lead", "feature", "vertical", "horizontal"}:
            assert story.select_one(".home-media img") is not None, story.get("data-route")


def test_projected_media_labels_use_story_headline_not_internal_rationale(tmp_path: Path) -> None:
    site = _build(tmp_path)

    frames = _soup(site / "issues/002/index.html").select(".preview-media iframe")
    assert [frame.get("title") for frame in frames] == [f"Video: {slug}" for slug in ISSUE_002_SLUGS]
    for route in ("index.html", "issues/002/index.html"):
        page = (site / route).read_text(encoding="utf-8")
        assert "Internal editorial rationale" not in page, route
        assert "Rights holder" not in page, route


def test_issue_001_keeps_image_heroes_and_receives_no_video_projection(tmp_path: Path) -> None:
    """D: Issue 001 stays isolated from Issue 002's preview-media treatment."""
    site = _build(tmp_path)

    page = _soup(site / "issues/001/index.html")
    heroes = page.select(".story-preview .hero")
    assert len(heroes) == 4
    assert len(page.select(".story-preview .hero img")) == 4
    assert page.select(".preview-media") == []
    assert page.select("iframe") == []


def test_issue_dates_come_from_metadata_and_the_home_date_does_not(tmp_path: Path) -> None:
    """E: every fixture issue bakes 2026-01-01; metadata must correct the edition surfaces.

    The homepage previously inherited `ISSUE_METADATA[latest]["date"]`, which is why `/` announced
    a date four days in the future. An edition date belongs to the edition; `/` states the current
    publication date instead.
    """
    site = _build(tmp_path)

    expected = {
        "issues/002/index.html": "2026-08-23",
        "issues/001/index.html": "2026-08-09",
    }
    for route, published in expected.items():
        node = _soup(site / route).select_one(".issue-date time")
        assert node is not None, route
        assert node.get("datetime") == published, route
        assert node.get_text(strip=True) != "Thursday, January 1, 2026", route

    home = _soup(site / "index.html")
    assert home.select_one(".issue-date") is None, "the front page is not an edition"
    stamp = home.select_one(".home-datestamp time")
    assert stamp is not None
    assert stamp.get("datetime") not in {"2026-08-23", "2026-08-09"}

    archive = _soup(site / "archive/index.html")
    assert [node.get("datetime") for node in archive.select(".archive-list time")] == [
        "2026-08-23",
        "2026-08-09",
    ]
    assert archive.select_one('header.site-header a.brand[href="../"]')


def test_home_date_is_the_current_new_york_date_from_an_injectable_clock(tmp_path: Path) -> None:
    """The site date is generated, never baked, and it is generated in the newsroom's timezone."""
    issues = tmp_path / "issues"
    _issue(issues, "001", ISSUE_001_SLUGS, baked_media=True)
    _issue(issues, "002", ISSUE_002_SLUGS)
    site = tmp_path / "site"

    # 03:30 UTC on the 21st is still the evening of the 20th in New York.
    pinned = datetime(2026, 8, 21, 3, 30, tzinfo=timezone.utc)
    assemble_site(("001", "002"), issues_root=issues, site_dir=site, run_pagefind=False, clock=pinned)

    stamp = _soup(site / "index.html").select_one(".home-datestamp time")
    assert stamp.get("datetime") == "2026-08-20"
    assert stamp.get_text(strip=True) == "Thursday, August 20, 2026"

    assert site_date(pinned).isoformat() == "2026-08-20"
    assert site_date(datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc)).isoformat() == "2026-08-20"
    # and with no clock at all it still resolves to a New York date rather than the host's
    assert site_date() == datetime.now(ZoneInfo("America/New_York")).date()


def test_unknown_issue_metadata_fails_loudly(tmp_path: Path) -> None:
    """F: Issue 003 must not silently publish an empty or stale date."""
    issues = tmp_path / "issues"
    _issue(issues, "003", ISSUE_002_SLUGS)

    with pytest.raises(ValueError) as exc:
        assemble_site(("003",), issues_root=issues, site_dir=tmp_path / "site", run_pagefind=False)
    message = str(exc.value)
    assert "003" in message
    assert "ISSUE_METADATA" in message


def test_missing_selected_media_fails_loudly(tmp_path: Path) -> None:
    """The original defect was a preview-less release. It must now stop the build."""
    issues = tmp_path / "issues"
    _issue(issues, "001", ISSUE_001_SLUGS, baked_media=True)
    _issue(issues, "002", ISSUE_002_SLUGS)
    manifest_path = issues / "002" / "media" / "media_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["3"]["video_url"] = ""
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError) as exc:
        assemble_site(("001", "002"), issues_root=issues, site_dir=tmp_path / "site", run_pagefind=False)
    assert "readable-three" in str(exc.value)


def test_absent_manifest_fails_loudly_for_hero_less_previews(tmp_path: Path) -> None:
    issues = tmp_path / "issues"
    _issue(issues, "001", ISSUE_001_SLUGS, baked_media=True)
    _issue(issues, "002", ISSUE_002_SLUGS)
    (issues / "002" / "media" / "media_manifest.json").unlink()

    with pytest.raises(FileNotFoundError) as exc:
        assemble_site(("001", "002"), issues_root=issues, site_dir=tmp_path / "site", run_pagefind=False)
    assert "selected-media manifest" in str(exc.value)


def test_archive_is_discoverable_from_every_page_with_footer_navigation(tmp_path: Path) -> None:
    """G: explicit expected counts rather than a vacuous all()."""
    site = _build(tmp_path)

    with_footer = sorted(
        path.relative_to(site).as_posix()
        for path in site.rglob("*.html")
        if _soup(path).select_one("footer.site-footer nav")
    )
    assert with_footer == sorted(
        [
            "archive/index.html",
            "index.html",
            "issues/001/index.html",
            "issues/002/index.html",
            "search/index.html",
            *PUBLIC_PAGES,
        ]
    )
    for route in with_footer:
        page = _soup(site / route)
        links = page.select("footer.site-footer nav a[data-site-archive]")
        assert len(links) == 1, route
        depth = len([part for part in Path(route).parent.parts if part != "."])
        assert links[0].get("href") == ("../" * depth or "./") + "archive/", route


def test_masthead_orders_logo_then_subscribe_then_search_on_every_page(tmp_path: Path) -> None:
    """The header is projected on every route, not only the home page."""
    site = _build(tmp_path)

    routes = sorted(
        path.relative_to(site).as_posix()
        for path in site.rglob("*.html")
        if _soup(path).select_one("header.site-header")
    )
    assert routes == sorted(
        [
            "archive/index.html",
            "index.html",
            "issues/001/index.html",
            "issues/002/index.html",
            "search/index.html",
            *PUBLIC_PAGES,
        ]
    )
    for route in routes:
        header = _soup(site / route).select_one("header.site-header")
        rows = [child.get("class") for child in header.find_all(recursive=False)]
        assert rows == [["header-main"], ["lane-nav"]], route

        primary = [child.get("class") for child in header.select_one(".header-main").find_all(recursive=False)]
        assert primary == [["brand"], ["header-actions"]], route

        actions = header.select_one(".header-actions").find_all(recursive=False)
        assert [child.get("class") for child in actions] == [["subscribe-control"], ["site-search"]], route

        # the search kept the wiring assets/ksignal.js and the QA tools select on
        search = header.select_one(".site-search")
        assert search.get("data-pagefind-url"), route
        assert search.select_one(".search-toggle") and search.select_one(".search-form input"), route
        assert search.select_one(".search-typeahead") is not None, route


def test_subscribe_control_promises_no_destination(tmp_path: Path) -> None:
    """No newsletter or mailing-list mechanism exists in this repo, so it must not claim one."""
    site = _build(tmp_path)

    subscribe = _soup(site / "index.html").select_one(".subscribe-control")
    assert subscribe.name == "button"
    assert subscribe.get("type") == "button"
    assert subscribe.get("href") is None
    assert subscribe.get("aria-disabled") == "true"
    assert subscribe.get_text(strip=True) == "Subscribe"


def test_partial_masthead_fails_loudly(tmp_path: Path) -> None:
    """A header that lost its search or lane nav must stop the build, not ship unstyled."""
    issues = tmp_path / "issues"
    _issue(issues, "001", ISSUE_001_SLUGS, baked_media=True)
    _issue(issues, "002", ISSUE_002_SLUGS)
    home = issues / "002" / "newsletter.html"
    home.write_text(
        home.read_text(encoding="utf-8").replace('<nav class="lane-nav"', '<nav class="lane-rail"'),
        encoding="utf-8",
    )

    with pytest.raises(ValueError) as exc:
        assemble_site(("001", "002"), issues_root=issues, site_dir=tmp_path / "site", run_pagefind=False)
    assert "nav.lane-nav" in str(exc.value)


def test_interpretive_section_is_marked_without_touching_editorial_copy(tmp_path: Path) -> None:
    site = _build(tmp_path)

    for slug in ISSUE_002_SLUGS:
        article = _soup(site / f"articles/{slug}/index.html")
        sections = article.select(".article-body .internet-read")
        assert len(sections) == 1, slug
        assert sections[0].select_one("h2").get_text(strip=True) == "What the Internet Is Really Saying"
        assert sections[0].select_one("p").get_text(strip=True) == f"The interpretive read for {slug}."
        # the sibling section is untouched
        assert article.select_one(".translation").get("class") == ["translation"]


@contextmanager
def _served_site() -> Iterator[str]:
    """Serve the built site over HTTP so layout can be measured in a real engine."""
    import functools
    import http.server
    import socketserver
    import threading

    site = Path("outputs/site")
    if not (site / "index.html").is_file():
        pytest.skip("outputs/site has not been assembled")
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(site.resolve()))
    with socketserver.TCPServer(("127.0.0.1", 0), handler) as server:
        server.daemon_threads = True
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            yield f"http://127.0.0.1:{server.server_address[1]}/"
        finally:
            server.shutdown()


MASTHEAD_MEASURE = """() => {
    const box = el => el.getBoundingClientRect();
    // The visible control, not `.lane-item`: the item carries negative-margin hover padding that
    // overhangs the row it sits in and would measure the touch target rather than the layout.
    const items = Array.from(document.querySelectorAll('header.site-header .lane-trigger'));
    const edges = items.map(box);
    return {
        innerWidth: window.innerWidth,
        scrollWidth: document.documentElement.scrollWidth,
        headerLeft: box(document.querySelector('header.site-header')).left,
        brand: box(document.querySelector('header.site-header a.brand')),
        subscribe: box(document.querySelector('header.site-header .subscribe-control')),
        search: box(document.querySelector('header.site-header .site-search')),
        primaryBottom: box(document.querySelector('header.site-header .header-main')).bottom,
        laneTop: Math.min(...edges.map(e => e.top)),
        laneLeft: Math.min(...edges.map(e => e.left)),
        laneRight: Math.max(...edges.map(e => e.right)),
        laneNavLeft: box(document.querySelector('header.site-header .lane-nav')).left,
        laneCount: items.length
    };
}"""


def test_masthead_geometry_holds_across_viewports() -> None:
    """The layout requirement is geometric, so it is measured rather than inferred from CSS.

    Page-centred means centred on the viewport axis. Asserting the lane group's own centre against
    `innerWidth / 2` is the only check that fails if the group is ever centred inside the header's
    left column or dragged off-axis by the logo.

    On a phone the row is one scrolling strip instead, where a centre is not a meaningful thing to
    measure: its content is wider than its container by design. The equivalent guarantee there is
    that the strip starts on the same content inset as the rest of the header, so the check swaps
    rather than lapsing.
    """
    playwright = pytest.importorskip("playwright.sync_api")

    with _served_site() as base:
        try:
            with playwright.sync_playwright() as driver:
                browser = driver.chromium.launch()
                try:
                    for width in (1600, 1440, 1280, 1024, 820, 600, 390):
                        page = browser.new_page(viewport={"width": width, "height": 900})
                        page.goto(base, wait_until="domcontentloaded")
                        m = page.evaluate(MASTHEAD_MEASURE)
                        page.close()
                        at = f"{width}px"
                        assert m["laneCount"] == 5, at
                        assert m["scrollWidth"] <= width, f"{at}: horizontal overflow"

                        # logo pinned to the header's left content edge
                        assert m["brand"]["left"] - m["headerLeft"] <= 24, at
                        # Subscribe precedes Search, and Search is the furthest-right control
                        assert m["subscribe"]["right"] <= m["search"]["left"], at
                        assert m["search"]["right"] > m["subscribe"]["right"], at
                        assert m["search"]["right"] > m["brand"]["right"], at
                        # the lane group sits on its own row beneath the primary row
                        assert m["laneTop"] >= m["primaryBottom"], at
                        if width > 640:
                            # and is centred on the page axis, not on the header's left column
                            centre = (m["laneLeft"] + m["laneRight"]) / 2
                            assert abs(centre - width / 2) <= 2, f"{at}: lane centre {centre} vs {width / 2}"
                        else:
                            # the scrolling strip starts on the header's own content inset
                            assert abs(m["laneLeft"] - m["laneNavLeft"]) <= 2, at
                            assert m["laneNavLeft"] - m["headerLeft"] <= 24, at
                            assert m["laneLeft"] - m["brand"]["left"] <= 2, at
                finally:
                    browser.close()
        except Exception as exc:  # no browser binary available in this environment
            if "Executable doesn" in str(exc) or "playwright install" in str(exc):
                pytest.skip(f"playwright browser unavailable: {exc}")
            raise


def test_every_lane_popover_fits_the_tablet_viewport() -> None:
    """Geometry regression for the centred tablet lane row.

    A right-anchored 240px popover resolved to a negative left edge for the first lane between
    the phone and tablet breakpoints. Overflow is a layout fact, not a markup fact, so this runs
    the real built site through a browser rather than asserting on CSS text.
    """
    site = Path("outputs/site")
    if not (site / "index.html").is_file():
        pytest.skip("outputs/site has not been assembled")
    playwright = pytest.importorskip("playwright.sync_api")

    import functools
    import http.server
    import socketserver
    import threading

    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(site.resolve()))
    with socketserver.TCPServer(("127.0.0.1", 0), handler) as server:
        server.daemon_threads = True
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{server.server_address[1]}/"
        measure = """() => Array.from(document.querySelectorAll('.lane-item')).map(item => {
            item.classList.add('is-open');
            const box = item.querySelector('.lane-popover').getBoundingClientRect();
            item.classList.remove('is-open');
            return {
                label: item.querySelector('.lane-trigger').textContent.trim(),
                left: box.left, right: box.right, width: box.width,
                innerWidth: window.innerWidth,
                scrollWidth: document.documentElement.scrollWidth
            };
        })"""
        try:
            with playwright.sync_playwright() as driver:
                browser = driver.chromium.launch()
                try:
                    for width in (768, 820):
                        page = browser.new_page(viewport={"width": width, "height": 1024})
                        page.goto(base, wait_until="domcontentloaded")
                        lanes = page.evaluate(measure)
                        page.close()
                        assert len(lanes) == 5, f"{width}px: expected 5 lanes, found {len(lanes)}"
                        for lane in lanes:
                            assert lane["width"] > 0, f"{width}px {lane['label']}: popover has no box"
                            assert lane["left"] >= 0, f"{width}px {lane['label']}: left {lane['left']}"
                            assert lane["right"] <= lane["innerWidth"], (
                                f"{width}px {lane['label']}: right {lane['right']} > {lane['innerWidth']}"
                            )
                        assert lanes[0]["scrollWidth"] <= width, f"{width}px: horizontal overflow"
                finally:
                    browser.close()
        except Exception as exc:  # no browser binary available in this environment
            if "Executable doesn" in str(exc) or "playwright install" in str(exc):
                pytest.skip(f"playwright browser unavailable: {exc}")
            raise
        finally:
            server.shutdown()


def test_a_real_tap_opens_and_closes_every_lane_on_a_touch_device() -> None:
    """Interaction regression for the phone lane strip. Taps, never ``classList``.

    The tablet test above proves geometry by adding ``.is-open`` itself, which cannot see anything
    the tap path does: it never exercises the capability predicate, the click handler, the lift out
    of the scroll container, or the close paths. That gap is what let a production failure ship.

    The decisive assertion here is the hit test. ``getBoundingClientRect`` reports an element's own
    box whether or not an ancestor clips it away, and Playwright's visibility check agrees with it,
    so a popover clipped to nothing still measures as a full-size visible box. Only asking the
    document what is actually painted at the popover's centre can tell the difference.
    """
    site = Path("outputs/site")
    if not (site / "index.html").is_file():
        pytest.skip("outputs/site has not been assembled")
    playwright = pytest.importorskip("playwright.sync_api")

    import functools
    import http.server
    import socketserver
    import threading

    # A lifted popover is no longer a descendant of its lane, so it is resolved through the handle
    # the interaction script keeps rather than by looking inside `.lane-item`.
    state_of = """(index) => {
        const items = Array.from(document.querySelectorAll('.lane-item'));
        const item = items[index];
        const popover = item.__lanePopover || item.querySelector('.lane-popover');
        const box = popover.getBoundingClientRect();
        const centre = document.elementFromPoint(box.left + box.width / 2, box.top + box.height / 2);
        return {
            expanded: item.querySelector('.lane-trigger').getAttribute('aria-expanded'),
            isOpen: item.classList.contains('is-open'),
            width: box.width, height: box.height,
            left: box.left, top: box.top, right: box.right, bottom: box.bottom,
            paintedAtCentre: !!(centre && popover.contains(centre)),
            openCount: document.querySelectorAll('.lane-item.is-open').length,
            restored: items.every(node => {
                const own = node.__lanePopover || node.querySelector('.lane-popover');
                return own ? own.parentElement === node : true;
            }),
            innerWidth: window.innerWidth, innerHeight: window.innerHeight,
            scrollWidth: document.documentElement.scrollWidth,
        };
    }"""

    # Somewhere off the lanes that is not itself a control, so tapping it cannot navigate away.
    outside_point = """() => {
        for (let y = window.innerHeight - 20; y > 0; y -= 10) {
            for (const x of [window.innerWidth / 2, 8, window.innerWidth - 8]) {
                const node = document.elementFromPoint(x, y);
                if (!node) continue;
                if (node.closest('.lane-item, .lane-popover, a, button, input')) continue;
                return {x, y};
            }
        }
        return null;
    }"""

    def assert_open(state: dict, label: str, engine: str) -> None:
        where = f"{engine} {label}"
        assert state["expanded"] == "true", f"{where}: aria-expanded is {state['expanded']!r}"
        assert state["isOpen"], f"{where}: lane did not gain .is-open"
        assert state["openCount"] == 1, f"{where}: {state['openCount']} lanes open, expected 1"
        assert state["width"] > 0 and state["height"] > 0, f"{where}: popover box is empty"
        assert state["top"] >= 0 and state["bottom"] <= state["innerHeight"], (
            f"{where}: popover spans {state['top']}-{state['bottom']} outside {state['innerHeight']}px"
        )
        assert state["left"] >= 0 and state["right"] <= state["innerWidth"], (
            f"{where}: popover spans {state['left']}-{state['right']} outside {state['innerWidth']}px"
        )
        # The regression itself: a clipped popover keeps its box and loses its pixels.
        assert state["paintedAtCentre"], (
            f"{where}: nothing of the popover is painted at its own centre — it is open in the DOM "
            "but clipped away, which is what a phone shows as a dropdown that will not open"
        )

    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(site.resolve()))
    with socketserver.TCPServer(("127.0.0.1", 0), handler) as server:
        server.daemon_threads = True
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{server.server_address[1]}/"
        exercised: list[str] = []
        try:
            with playwright.sync_playwright() as driver:
                for engine in ("chromium", "webkit"):
                    try:
                        browser = getattr(driver, engine).launch()
                    except Exception as exc:  # engine not installed in this environment
                        if "Executable doesn" in str(exc) or "playwright install" in str(exc):
                            continue
                        raise
                    try:
                        context = browser.new_context(
                            viewport={"width": 390, "height": 844},
                            has_touch=True,
                            is_mobile=True,
                        )
                        page = context.new_page()
                        errors: list[str] = []
                        page.on("pageerror", lambda error: errors.append(str(error)))
                        page.goto(base, wait_until="load")
                        page.wait_for_timeout(200)

                        triggers = page.locator(".lane-item .lane-trigger")
                        lanes = triggers.count()
                        assert lanes == 5, f"{engine}: expected 5 lane controls, found {lanes}"

                        # Every lane, including the ones only reachable by scrolling the strip.
                        for index in range(lanes):
                            triggers.nth(index).scroll_into_view_if_needed()
                            triggers.nth(index).tap()
                            page.wait_for_timeout(160)
                            assert_open(page.evaluate(state_of, index), f"lane {index}", engine)

                        # Tapping the same lane again closes it.
                        triggers.nth(0).scroll_into_view_if_needed()
                        triggers.nth(0).tap()
                        page.wait_for_timeout(160)
                        assert_open(page.evaluate(state_of, 0), "lane 0 reopened", engine)
                        triggers.nth(0).tap()
                        page.wait_for_timeout(160)
                        closed = page.evaluate(state_of, 0)
                        assert not closed["isOpen"], f"{engine}: a second tap left lane 0 open"
                        assert closed["expanded"] == "false", f"{engine}: aria-expanded stayed true"
                        assert closed["openCount"] == 0, f"{engine}: {closed['openCount']} lanes open"

                        # Tapping another lane closes the first.
                        triggers.nth(0).tap()
                        page.wait_for_timeout(160)
                        triggers.nth(1).scroll_into_view_if_needed()
                        triggers.nth(1).tap()
                        page.wait_for_timeout(160)
                        first = page.evaluate(state_of, 0)
                        assert not first["isOpen"], f"{engine}: lane 0 stayed open behind lane 1"
                        assert first["expanded"] == "false", f"{engine}: lane 0 aria-expanded stayed true"
                        assert_open(page.evaluate(state_of, 1), "lane 1 after lane 0", engine)

                        # Tapping outside closes everything and returns every popover to its lane.
                        point = page.evaluate(outside_point)
                        assert point, f"{engine}: found no neutral point to tap outside the lanes"
                        page.touchscreen.tap(point["x"], point["y"])
                        page.wait_for_timeout(200)
                        outside = page.evaluate(state_of, 1)
                        assert outside["openCount"] == 0, f"{engine}: a tap outside left lanes open"
                        assert outside["expanded"] == "false", f"{engine}: aria-expanded stayed true"
                        assert outside["restored"], (
                            f"{engine}: a popover was left lifted out of its lane after closing"
                        )

                        # Escape closes it too.
                        triggers.nth(1).tap()
                        page.wait_for_timeout(160)
                        page.keyboard.press("Escape")
                        page.wait_for_timeout(200)
                        escaped = page.evaluate(state_of, 1)
                        assert escaped["openCount"] == 0, f"{engine}: Escape left lanes open"
                        assert escaped["restored"], f"{engine}: Escape left a popover lifted"

                        assert outside["scrollWidth"] <= 390, (
                            f"{engine}: the page overflows horizontally ({outside['scrollWidth']}px)"
                        )

                        # Second pass with the lane strip as a containing block for fixed
                        # descendants. That is what a phone does with a composited scroller, and it
                        # is the condition the shipped build failed under: `position:fixed` stops
                        # escaping `.lane-nav`, and the popover is clipped to a 56px row while every
                        # box measurement and visibility check still reports it as fine. Desktop
                        # engines never enter that state on their own, so the test asks for it.
                        page.add_style_tag(
                            content="@media(max-width:640px){.lane-nav{will-change:transform}}"
                        )
                        page.wait_for_timeout(120)
                        for index in range(lanes):
                            triggers.nth(index).scroll_into_view_if_needed()
                            triggers.nth(index).tap()
                            page.wait_for_timeout(160)
                            assert_open(
                                page.evaluate(state_of, index),
                                f"lane {index} with a composited lane strip",
                                engine,
                            )

                        assert not errors, f"{engine}: page errors {errors}"
                        exercised.append(engine)
                        page.close()
                        context.close()
                    finally:
                        browser.close()
        finally:
            server.shutdown()

    if not exercised:
        pytest.skip("no playwright browser is installed")


def test_homepage_is_not_a_copy_of_the_latest_issue(tmp_path: Path) -> None:
    """`/` is a front page over the publication, not the current edition rendered again."""
    site = _build(tmp_path)

    home = _soup(site / "index.html")
    issue = _soup(site / "issues/002/index.html")

    assert home.select_one("main.home-shell") is not None
    assert home.select_one("main .front-page") is None, "the homepage must not reuse the issue grid"
    assert issue.select_one("main .front-page") is not None, "the issue page keeps its own layout"
    assert home.select(".home-story"), "the homepage renders its own story cards"
    assert issue.select(".story-preview"), "the issue page keeps its previews"
    assert home.select_one("main .issue-kicker") is None, "per-card edition kickers do not belong on /"


def test_article_body_copy_is_never_the_homepage_identity(tmp_path: Path) -> None:
    """"What the Internet Is Really Saying" is a section inside an article and nothing else.

    It was the homepage `<h1>`, which made an article's interpretive heading the name of the
    publication and put it into every surface generated from the front page.
    """
    site = _build(tmp_path)
    home = _soup(site / "index.html")
    leaked = "what the internet is really saying"

    heading = home.select_one("h1")
    assert heading is not None
    assert leaked not in heading.get_text(" ", strip=True).casefold()
    assert "K-Signal" in heading.get_text(" ", strip=True), "the h1 names the publication"

    for selector in ("main", "title", ".home-pkg-label", ".home-head", ".home-dek", ".home-standfirst"):
        for node in home.select(selector):
            assert leaked not in node.get_text(" ", strip=True).casefold(), selector
    # Not in the tab, a bookmark, a share card, or anything else generated from the document head.
    assert leaked not in str(home.select_one("head") or "").casefold()
    assert home.select_one("title").get_text(strip=True).startswith("K-Signal")
    for meta in home.select('meta[name="description"], meta[property="og:title"]'):
        assert leaked not in str(meta.get("content", "")).casefold()
    # The issue page it was copied from is an edition and keeps whatever it published with.
    assert leaked in (site / "issues/002/index.html").read_text(encoding="utf-8").casefold()

    # It is still where it belongs, and it is still indexable there.
    article = _soup(site / f"articles/{ISSUE_002_SLUGS[0]}/index.html")
    assert article.select_one(".article-body .internet-read h2").get_text(strip=True) == (
        "What the Internet Is Really Saying"
    )


def test_homepage_composes_one_pool_and_is_not_segmented_by_issue(tmp_path: Path) -> None:
    """Issue membership is metadata. It must not be the page's structure or its ranking.

    The previous front page was "Issue 002" then an "Earlier signals" list, so every story from
    the newer edition automatically outranked every story from the older one.
    """
    site = _build(tmp_path)
    home = _soup(site / "index.html")

    stories = home.select("article.home-story")
    assert len(stories) == 8, "every publishable story is on the front page"

    text = (site / "index.html").read_text(encoding="utf-8")
    assert "Earlier signals" not in text
    for issue in ("001", "002"):
        assert f"Issue {issue}" not in text, "an edition number is not a homepage section"

    # No section, package or heading is an issue container.
    for container in home.select("main section, main .home-package, main .home-rows"):
        issues = {story.get("data-issue-id") for story in container.select("article.home-story")}
        assert issues != {"001"} and issues != {"002"} or len(container.select("article.home-story")) <= 1, (
            f"{container.get('class')} groups a single edition"
        )

    # Both editions reach the front package, and both reach a role that carries media.
    front = home.select_one(".home-package--front")
    assert {story.get("data-issue-id") for story in front.select("article.home-story")} == {"001", "002"}
    with_media = {
        story.get("data-issue-id") for story in home.select("article.home-story") if story.select_one(".home-media")
    }
    assert with_media == {"001", "002"}
    assert home.select_one('article.home-story[data-role="lead"]') is not None


def test_homepage_gives_every_story_one_role_and_two_editorial_packages(tmp_path: Path) -> None:
    site = _build(tmp_path)
    home = _soup(site / "index.html")

    roles = [story.get("data-role") for story in home.select("article.home-story")]
    assert roles.count("lead") == 1, "exactly one lead"
    assert len(set(roles)) >= 3, "the front page is not a grid of equal cards"
    assert home.select_one('.home-story[data-role="lead"] .home-dek') is not None
    assert home.select('.home-story[data-role="compact"] .home-dek') == [], "compact rows are headline-only"

    packages = home.select("main .home-package")
    assert len(packages) == 2, "at least two coherent editorial packages"
    assert home.select_one(".home-pkg-label").get_text(strip=True) == "More signals"

    # The lead's picture is the one the browser should fetch first.
    lead_image = home.select_one('.home-story[data-role="lead"] .home-media img')
    assert lead_image.get("loading") == "eager"
    assert lead_image.get("fetchpriority") == "high"
    assert all(
        img.get("loading") == "lazy"
        for img in home.select('.home-story:not([data-role="lead"]) .home-media img')
    )


def test_homepage_links_resolve_to_documents_that_exist(tmp_path: Path) -> None:
    site = _build(tmp_path)
    home = _soup(site / "index.html")

    routes = [str(node.get("href")) for node in home.select(".home-head a[href]")]
    assert sorted(routes) == sorted(
        [f"articles/{slug}/" for slug in ISSUE_002_SLUGS]
        + [f"issues/001/articles/{slug}.html" for slug in ISSUE_001_SLUGS]
    )
    for href in routes:
        target = site / href if href.endswith(".html") else site / href / "index.html"
        assert target.exists(), href


def test_issue_page_offers_a_visible_route_back_to_the_current_publication(tmp_path: Path) -> None:
    """An issue route is an archived edition, not an old homepage, and it must not be a trap."""
    site = _build(tmp_path)

    for issue in ("001", "002"):
        page = _soup(site / f"issues/{issue}/index.html")
        bar = page.select_one("main .edition-bar")
        assert bar is not None, issue
        home = bar.select_one("a[data-site-home]")
        assert home is not None and home.get("href") == "../../", issue
        assert (site / "index.html").exists()
        archive = bar.select_one('a[href="../../archive/"]')
        assert archive is not None, issue
        assert f"Issue {issue}" in bar.get_text(" ", strip=True), issue
        assert "Archived edition" in bar.get_text(" ", strip=True), issue

    # The front page is not an edition, so it carries no edition bar.
    assert _soup(site / "index.html").select_one(".edition-bar") is None


def test_article_urls_survive_a_later_issue(tmp_path: Path) -> None:
    """Publication-root article routes belong to the publication, not to whichever issue is newest.

    The previous rule minted `/articles/<slug>/` for the latest issue only, so every release
    deleted the previous issue's article URLs.
    """
    issues = tmp_path / "issues"
    _issue(issues, "001", ISSUE_001_SLUGS, baked_media=True)
    _issue(issues, "002", ISSUE_002_SLUGS)
    _issue(issues, "003", ("later-one", "later-two", "later-three", "later-four"))

    first = tmp_path / "site-a"
    assemble_site(("001", "002"), issues_root=issues, site_dir=first, run_pagefind=False)
    assert all((first / "articles" / slug / "index.html").exists() for slug in ISSUE_002_SLUGS)

    second = tmp_path / "site-b"
    with _registered_issue("003", "2026-09-06"):
        build = assemble_site(("001", "002", "003"), issues_root=issues, site_dir=second, run_pagefind=False)
    for slug in ISSUE_002_SLUGS:
        assert (second / "articles" / slug / "index.html").exists(), f"issue 002 lost /articles/{slug}/"
    for slug in ("later-one", "later-two", "later-three", "later-four"):
        assert (second / "articles" / slug / "index.html").exists(), slug
    assert set(build.article_routes) == {
        f"/articles/{slug}/" for slug in (*ISSUE_002_SLUGS, "later-one", "later-two", "later-three", "later-four")
    }

    # The non-routable issue is untouched: it has no slugs to promote, so its URLs never move.
    assert all((second / "issues/001/articles" / f"{slug}.html").exists() for slug in ISSUE_001_SLUGS)
    assert not (second / "articles" / ISSUE_001_SLUGS[0]).exists()


def test_duplicate_article_slug_across_issues_fails_loudly(tmp_path: Path) -> None:
    issues = tmp_path / "issues"
    _issue(issues, "001", ISSUE_001_SLUGS, baked_media=True)
    _issue(issues, "002", ISSUE_002_SLUGS)
    _issue(issues, "003", ISSUE_002_SLUGS)

    with _registered_issue("003", "2026-09-06"):
        with pytest.raises(ValueError, match="claimed by both issue 002 and issue 003"):
            assemble_site(("001", "002", "003"), issues_root=issues, site_dir=tmp_path / "site", run_pagefind=False)


def test_every_page_declares_the_one_url_that_owns_it(tmp_path: Path) -> None:
    site = _build(tmp_path)

    expected = {
        "index.html": "/",
        "archive/index.html": "/archive/",
        "search/index.html": "/search/",
        "issues/002/index.html": "/issues/002/",
        "about.html": "/about.html",
        f"articles/{ISSUE_002_SLUGS[0]}/index.html": f"/articles/{ISSUE_002_SLUGS[0]}/",
        f"issues/001/articles/{ISSUE_001_SLUGS[0]}.html": f"/issues/001/articles/{ISSUE_001_SLUGS[0]}.html",
    }
    for route, canonical in expected.items():
        node = _soup(site / route).select_one('link[rel="canonical"]')
        assert node is not None, route
        assert str(node.get("href")).endswith(canonical), route
        assert str(node.get("href")).startswith("https://"), route

    # The article's machine-readable route agrees with the URL it is actually served from.
    shell = _soup(site / f"articles/{ISSUE_002_SLUGS[0]}/index.html").select_one("main.article-shell")
    if shell is not None:
        assert shell.get("data-route") == f"articles/{ISSUE_002_SLUGS[0]}/"


def test_search_indexes_articles_only(tmp_path: Path) -> None:
    """Discovery surfaces route to stories; they must not compete with them in results.

    `/`, the issue pages, `/archive/` and `/search/` were each indexed as their own result, which
    is why searching surfaced the front-page headline and "Archive" instead of articles.
    """
    site = _build(tmp_path)

    indexed = {
        path.relative_to(site).as_posix()
        for path in site.rglob("*.html")
        if _soup(path).select_one("[data-pagefind-body]") is not None
    }
    assert indexed == {
        *(f"articles/{slug}/index.html" for slug in ISSUE_002_SLUGS),
        *(f"issues/001/articles/{slug}.html" for slug in ISSUE_001_SLUGS),
    }
    for route in ("index.html", "archive/index.html", "search/index.html", "issues/002/index.html"):
        assert _soup(site / route).select_one("body[data-pagefind-ignore]") is not None, route


def test_masthead_controls_keep_their_assigned_shapes(tmp_path: Path) -> None:
    """Subscribe is a flat black rectangle; Search stays the only rounded control."""
    site = _build(tmp_path)
    css = "".join(
        node.get_text() for node in _soup(site / "index.html").select("style[data-persistent-site-presentation]")
    )

    subscribe = css.split(".subscribe-control{", 1)[1].split("}", 1)[0]
    assert "border-radius:0" in subscribe
    assert "background:#000" in subscribe
    assert "color:#fff" in subscribe
    assert "border-radius:999px" in css.split(".site-search{", 1)[1].split("}", 1)[0]


def test_interpretive_module_wears_the_red_rail_as_a_whole_block(tmp_path: Path) -> None:
    """The rail belongs to the module, not to its heading.

    With the rail on the `h2` alone the interpretation read as a decorated heading followed by
    loose paragraphs. It now spans heading and body, with no card border, no shadow and no radius,
    over a navy wash kept light enough to separate the passage without making it a panel.
    """
    site = _build(tmp_path)
    css = "".join(
        node.get_text()
        for node in _soup(site / f"articles/{ISSUE_002_SLUGS[0]}/index.html").select(
            "style[data-persistent-site-presentation]"
        )
    )

    block = css.split(".article-body .internet-read{", 1)[1].split("}", 1)[0]
    assert "border-left:3px solid var(--red)" in block, "the rail spans the whole module"
    assert "border-radius:0" in block
    assert "box-shadow:none" in block
    assert "background:#16305e0a" in block, "a subtle navy wash under the whole module"

    heading = css.split(".article-body .internet-read h2{", 1)[1].split("}", 1)[0]
    assert "border-left:0" in heading, "the heading no longer owns the rail"
    assert "text-transform:uppercase" in heading and "11px" in heading, "a utility label"
    body = css.split(".article-body .internet-read p{", 1)[1].split("}", 1)[0]
    assert "font-size:18px" in body, "body copy stays at the article's reading size"


def test_requires_completed_issue(tmp_path: Path) -> None:
    try:
        assemble_site(("999",), issues_root=tmp_path, site_dir=tmp_path / "site", run_pagefind=False)
    except FileNotFoundError as exc:
        assert "newsletter.html" in str(exc)
    else:
        raise AssertionError("missing issue should fail")


def test_pagefind_page_count_reads_page_total() -> None:
    output = "Indexed 1 language\nIndexed 13 pages\nIndexed 190 words\nIndexed 1 filter"
    assert _pagefind_page_count(output) == 13


# How many editions of what size add up to each probed pool. The publication grows by publishing
# more editions and by editions of different lengths, so both are exercised; 001 stays baked-media
# because that is the shape of the one edition that predates article packages.
POOL_SHAPES: dict[int, tuple[tuple[str, int], ...]] = {
    9: (("001", 4), ("002", 5)),
    10: (("001", 4), ("002", 3), ("003", 3)),
    12: (("001", 4), ("002", 4), ("003", 4)),
    16: (("001", 4), ("002", 4), ("003", 4), ("004", 4)),
}
POOL_DATES = {"001": "2026-08-09", "002": "2026-08-23", "003": "2026-09-06", "004": "2026-09-20"}


@pytest.mark.parametrize("total", sorted(POOL_SHAPES))
def test_homepage_composition_holds_as_the_pool_grows(tmp_path: Path, total: int) -> None:
    """The front page is a view over a pool, so growing the pool must not change what it is.

    Only the architecture is asserted. How many stories the second package ends up holding, what
    order they fall in beyond being distinct, and how any of it is drawn are editorial decisions
    that are meant to be free to change; a story losing its address, appearing twice, or the page
    silently regrouping itself by edition are not.
    """
    issues_root = tmp_path / "issues"
    names = tuple(issue for issue, _ in POOL_SHAPES[total])
    with ExitStack() as stack:
        for issue, count in POOL_SHAPES[total]:
            stack.enter_context(_registered_issue(issue, POOL_DATES[issue]))
            slugs = tuple(f"pool-{issue}-{index}" for index in range(1, count + 1))
            _issue(issues_root, issue, slugs, baked_media=issue == "001")
        site = tmp_path / "site"
        assemble_site(names, issues_root=issues_root, site_dir=site, run_pagefind=False)

    home = _soup(site / "index.html")
    front = home.select_one(".home-package--front")
    assert front is not None
    assert len(front.select("article.home-story")) == len(FRONT_ROLES), (
        "the front package is a fixed set of positions, not a share of the pool"
    )

    routes = [str(story.get("data-route")) for story in home.select("article.home-story")]
    assert all(routes), "every card states the address it routes to"
    assert len(set(routes)) == len(routes), "one story, one place on the front page"

    published = sorted(site.glob("articles/*/index.html")) + sorted(site.glob("issues/*/articles/*.html"))
    assert len(published) == total, "the fixture pool is the size the case says it is"
    assert len(routes) == len(published), "every published article reaches the front page"

    for article in published:
        canonical = _soup(article).select("link[rel='canonical']")
        assert len(canonical) == 1, f"{article.name} must claim exactly one address"

    assert home.select("main iframe") == [], "the front page ships no embedded player at any size"

    # Issue membership is metadata. It may label a card, but it must never become a container:
    # the moment it does, the homepage is a stack of editions again rather than one pool.
    for container in home.select("main section, main .home-package, main .home-rows"):
        assert not container.get("data-issue-id")
        assert not any("issue" in name for name in container.get("class", []))
    assert home.select("main .issue-kicker") == []
