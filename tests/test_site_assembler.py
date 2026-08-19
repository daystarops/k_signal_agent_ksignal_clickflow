import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from core.host_packager import validate_host_package
from core.site_assembler import PUBLIC_PAGES, _pagefind_page_count, assemble_site

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
        "item.classList.add('is-open');button.setAttribute('aria-expanded','true')",
        encoding="utf-8",
    )
    (issue_dir / "assets" / "logo.png").write_bytes(b"png")
    (issue_dir / "media" / "hero.jpg").write_bytes(b"jpg")
    hero = '<div class="hero"><img src="media/hero.jpg" alt="baked"></div>' if baked_media else ""
    links = "".join(
        f'<article class="story-preview {"lead" if index == 0 else "supporting"}">{hero}'
        f'<div class="preview-copy"><h2><a href="articles/{slug}.html">{slug}</a></h2>'
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
    (issue_dir / "newsletter.html").write_text(
        f'<html><head></head><body data-pagefind-body>{header}<main>{masthead}'
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
        manifest[str(index)] = {
            "video_url": f"https://www.youtube.com/embed/video{index}",
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
        assert "document.querySelectorAll('.lane-popover').forEach(p=>{p.style.top=''})" in text, route


def test_stale_interaction_source_fails_loudly(tmp_path: Path) -> None:
    issues = tmp_path / "issues"
    _issue(issues, "001", ISSUE_001_SLUGS, baked_media=True)
    _issue(issues, "002", ISSUE_002_SLUGS)
    (issues / "002" / "assets" / "ksignal.js").write_text("const mobile=()=>false;", encoding="utf-8")

    with pytest.raises(ValueError) as exc:
        assemble_site(("001", "002"), issues_root=issues, site_dir=tmp_path / "site", run_pagefind=False)
    assert "lane interaction source" in str(exc.value)


def test_selected_media_is_projected_on_root_and_permanent_issue_route(tmp_path: Path) -> None:
    """B and C: four projected previews on / and on /issues/002/."""
    site = _build(tmp_path)

    for route in ("index.html", "issues/002/index.html"):
        page = _soup(site / route)
        frames = page.select(".story-preview .hero.video.preview-media iframe")
        assert len(frames) == 4, route
        assert [frame.get("src") for frame in frames] == [
            f"https://www.youtube.com/embed/video{index}" for index in range(1, 5)
        ], route
        assert all(frame.get("allowfullscreen") == "" for frame in frames), route
        assert page.select(".story-preview .preview-media img") == [], route


def test_projected_media_labels_use_story_headline_not_internal_rationale(tmp_path: Path) -> None:
    site = _build(tmp_path)

    frames = _soup(site / "index.html").select(".preview-media iframe")
    assert [frame.get("title") for frame in frames] == [f"Video: {slug}" for slug in ISSUE_002_SLUGS]
    homepage = (site / "index.html").read_text(encoding="utf-8")
    assert "Internal editorial rationale" not in homepage
    assert "Rights holder" not in homepage


def test_issue_001_keeps_image_heroes_and_receives_no_video_projection(tmp_path: Path) -> None:
    """D: Issue 001 stays isolated from Issue 002's preview-media treatment."""
    site = _build(tmp_path)

    page = _soup(site / "issues/001/index.html")
    heroes = page.select(".story-preview .hero")
    assert len(heroes) == 4
    assert len(page.select(".story-preview .hero img")) == 4
    assert page.select(".preview-media") == []
    assert page.select("iframe") == []


def test_publication_dates_come_from_issue_metadata(tmp_path: Path) -> None:
    """E: every fixture issue bakes 2026-01-01; metadata must correct all three surfaces."""
    site = _build(tmp_path)

    expected = {
        "index.html": "2026-08-23",
        "issues/002/index.html": "2026-08-23",
        "issues/001/index.html": "2026-08-09",
    }
    for route, published in expected.items():
        node = _soup(site / route).select_one(".issue-date time")
        assert node is not None, route
        assert node.get("datetime") == published, route
        assert node.get_text(strip=True) != "Thursday, January 1, 2026", route

    archive = _soup(site / "archive/index.html")
    assert [node.get("datetime") for node in archive.select(".archive-list time")] == [
        "2026-08-23",
        "2026-08-09",
    ]
    assert archive.select_one('header.site-header a.brand[href="../"]')


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
        laneCount: items.length
    };
}"""


def test_masthead_geometry_holds_across_viewports() -> None:
    """The layout requirement is geometric, so it is measured rather than inferred from CSS.

    Page-centred means centred on the viewport axis. Asserting the lane group's own centre against
    `innerWidth / 2` is the only check that fails if the group is ever centred inside the header's
    left column or dragged off-axis by the logo.
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
                        # and is centred on the page axis, not on the header's left column
                        centre = (m["laneLeft"] + m["laneRight"]) / 2
                        assert abs(centre - width / 2) <= 2, f"{at}: lane centre {centre} vs {width / 2}"
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
