from pathlib import Path

from bs4 import BeautifulSoup

from core.link_checker import _homepage_lead_error, _persisted_article, check_local_page


def _newsletter(route: str, title: str, *, lead: bool = True) -> str:
    class_name = "story-preview lead" if lead else "story-preview"
    return (
        f'<article class="{class_name}"><a class="hero" href="{route}">media</a>'
        f'<h2><a href="{route}">{title}</a></h2>'
        f'<a class="read-signal" href="{route}">Read</a></article>'
    )


def test_resolves_rendered_readable_route_when_legacy_card_path_is_stale(tmp_path: Path) -> None:
    issue = tmp_path / "002"
    article = issue / "articles" / "readable-story.html"
    article.parent.mkdir(parents=True)
    article.write_text("story", encoding="utf-8")
    html = _newsletter("articles/readable-story.html", "Readable story")
    card = {
        "title": "Readable story",
        "article_path": str(issue / "articles" / "card_03.html"),
        "article_url": "articles/card_03.html",
    }

    path, route = _persisted_article(issue, card, html)

    assert path == article
    assert route == "articles/readable-story.html"
    assert check_local_page("03", str(path), html, route)["ok"] is True


def test_homepage_lead_accepts_any_persisted_current_issue_route() -> None:
    route = "articles/current-readable-lead.html"
    soup = BeautifulSoup(_newsletter(route, "Current lead"), "html.parser")

    assert _homepage_lead_error(soup, {route}) is None
    assert _homepage_lead_error(soup, {"articles/another.html"}) is not None


def test_article_check_does_not_require_an_absent_homepage_hero(tmp_path: Path) -> None:
    article = tmp_path / "story.html"
    article.write_text("story", encoding="utf-8")
    route = "articles/story.html"
    html = (
        f'<article class="story-preview"><h2><a href="{route}">Story</a></h2>'
        f'<a class="read-signal" href="{route}">Read</a></article>'
    )

    assert check_local_page("01", str(article), html, route)["ok"] is True
