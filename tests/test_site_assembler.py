from pathlib import Path

from bs4 import BeautifulSoup

from core.host_packager import validate_host_package
from core.site_assembler import PUBLIC_PAGES, assemble_site


def _issue(root: Path, issue: str, slugs: tuple[str, ...]) -> None:
    issue_dir = root / issue
    for dirname in ("articles", "assets", "media"):
        (issue_dir / dirname).mkdir(parents=True, exist_ok=True)
    (issue_dir / "assets" / "ksignal.css").write_text("body{}", encoding="utf-8")
    (issue_dir / "assets" / "ksignal.js").write_text("", encoding="utf-8")
    (issue_dir / "assets" / "logo.png").write_bytes(b"png")
    (issue_dir / "media" / "hero.jpg").write_bytes(b"jpg")
    links = "".join(f'<a href="articles/{slug}.html">{slug}</a>' for slug in slugs)
    common = '<a href="newsletter.html">home</a><a href="search.html">search</a><img src="assets/logo.png"><script src="assets/ksignal.js"></script>'
    (issue_dir / "newsletter.html").write_text(f"<html><body data-pagefind-body>{links}{common}</body></html>", encoding="utf-8")
    (issue_dir / "search.html").write_text(f'<html><body>{common}<div data-pagefind-url="./pagefind/pagefind.js"></div></body></html>', encoding="utf-8")
    for page in PUBLIC_PAGES:
        (issue_dir / page).write_text(f"<html><body>{common}</body></html>", encoding="utf-8")
    for slug in slugs:
        related = "".join(f'<a href="{other}.html">{other}</a>' for other in slugs if other != slug)
        (issue_dir / "articles" / f"{slug}.html").write_text(
            '<html><body data-pagefind-body><a href="../newsletter.html">issue</a>'
            '<a href="../search.html">search</a><img src="../media/hero.jpg">'
            f'<script src="../assets/ksignal.js"></script>{related}</body></html>', encoding="utf-8",
        )


def test_assembles_persistent_routes_without_mutating_issues(tmp_path: Path) -> None:
    issues = tmp_path / "issues"
    _issue(issues, "001", ("card_01",))
    _issue(issues, "002", ("readable-one", "readable-two"))
    before = (issues / "002" / "newsletter.html").read_bytes()
    site = tmp_path / "site"

    result = assemble_site(("001", "002"), issues_root=issues, site_dir=site, run_pagefind=False)

    assert result.issue_routes == ("/issues/001/", "/issues/002/")
    assert result.article_routes == ("/articles/readable-one/", "/articles/readable-two/")
    assert (site / "index.html").exists()
    assert (site / "issues/001/articles/card_01.html").exists()
    assert (site / "issues/002/index.html").exists()
    assert (site / "articles/readable-one/index.html").exists()
    assert (site / "archive/index.html").exists()
    assert (site / "search/index.html").exists()
    assert (issues / "002" / "newsletter.html").read_bytes() == before
    assert validate_host_package(site) == []

    homepage = BeautifulSoup((site / "index.html").read_text(encoding="utf-8"), "html.parser")
    assert homepage.select_one('a[href="articles/readable-one/"]')
    article = BeautifulSoup((site / "articles/readable-one/index.html").read_text(encoding="utf-8"), "html.parser")
    assert article.select_one('a[href="../../issues/002/"]')
    assert article.select_one('img[src="../../issues/002/media/hero.jpg"]')


def test_requires_completed_issue(tmp_path: Path) -> None:
    try:
        assemble_site(("999",), issues_root=tmp_path, site_dir=tmp_path / "site", run_pagefind=False)
    except FileNotFoundError as exc:
        assert "newsletter.html" in str(exc)
    else:
        raise AssertionError("missing issue should fail")
