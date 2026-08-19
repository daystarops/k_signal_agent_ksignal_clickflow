from __future__ import annotations

import json
from pathlib import Path

import pytest
from bs4 import BeautifulSoup
from pydantic import ValidationError

import ksignal.issue_builder as issue_builder
from ksignal.article_package import ArticlePackage
from ksignal.article_package_renderer import render_article_package
from ksignal.schema import SignalCard


ISSUE = "2099-02-02"


def _package(slug: str = "stadium-response", **changes: object) -> dict:
    value = {
        "story_id": "story-02", "issue_id": ISSUE, "editorial_slot": "card_02",
        "article_slug": slug, "lane": "sports",
        "headline": "Package headline must not replace legacy", "dek": "Package dek",
        "receipt": {"korean": "Package Korean receipt", "english": "Package English receipt"},
        "hero_media": None,
        "sections": [
            {"heading": "First depth heading", "purpose": "internal purpose one", "body": "First <unsafe> body.\n\nSecond paragraph.", "supporting_media": []},
            {"heading": "Second depth heading", "purpose": "internal purpose two", "body": "Second body.", "supporting_media": []},
            {"heading": "Third depth heading", "purpose": "internal purpose three", "body": "Third body.", "supporting_media": [
                {"path": "../media/ambulance.jpg", "caption": "Ambulance response", "credit": "Fixture desk", "source_url": "https://example.com/media", "rights_status": "supplied"}
            ]},
        ],
        "claim_limit": {"allowed": ["The club promised changes."], "prohibited": ["Do not infer intent."]},
        "sources": [{"label": "Club statement", "url": "https://example.com/source"}],
    }
    value.update(changes)
    return value


def _signal(number: int) -> SignalCard:
    return SignalCard(
        source=f"Source {number}", url=f"https://example.kr/story/{number}", category="sports",
        title_original=f"Original {number}", title_english=f"Signal {number}",
        raw_korean_excerpt=f"Legacy Korean {number}", literal_translation=f"Legacy English {number}",
        cultural_read=f"Cultural context {number}", business_read=f"Business context {number}",
        tags=["tag", f"number{number}"],
    )


def _write_package(root: Path, data: object, name: str = "package.json") -> Path:
    directory = root / ISSUE / "article_packages"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def test_strict_contract_and_supporting_media_cardinality() -> None:
    package = ArticlePackage.model_validate(_package())
    assert package.sections[0].supporting_media == []
    multi = _package()
    multi["sections"][0]["supporting_media"] = [
        {"path": "one.jpg", "caption": "one", "credit": "", "source_url": "", "rights_status": "given"},
        {"path": "two.jpg", "caption": "two", "credit": "", "source_url": "", "rights_status": "given"},
    ]
    assert len(ArticlePackage.model_validate(multi).sections[0].supporting_media) == 2
    with pytest.raises(ValidationError): ArticlePackage.model_validate({**_package(), "unexpected": True})
    with pytest.raises(ValidationError): ArticlePackage.model_validate({**_package(), "story_id": 2})
    with pytest.raises(ValidationError): ArticlePackage.model_validate({**_package(), "article_slug": "card_02"})
    assert ArticlePackage.model_validate({k: v for k, v in _package().items() if k != "hero_media"}).hero_media is None
    for field, value in (("lane", ""), ("headline", ""), ("dek", ""), ("sections", []), ("sources", [])):
        with pytest.raises(ValidationError): ArticlePackage.model_validate({**_package(), field: value})


def test_fragment_renderer_contract_order_media_and_sources() -> None:
    payload = _package()
    payload["sections"][2]["supporting_media"].append(
        {"path": "../media/second.jpg", "caption": "Second visual", "credit": "Other desk", "source_url": "https://example.com/second", "rights_status": "supplied"}
    )
    html = render_article_package(ArticlePackage.model_validate(payload))
    soup = BeautifulSoup(html, "html.parser")
    assert soup.select_one(".article-depth")
    assert len(soup.select(".article-depth")) == 1
    assert not soup.select(".article-package-depth")
    sections = soup.select(".article-section")
    assert [node.h2.get_text() for node in sections] == [item["heading"] for item in payload["sections"]]
    assert "<unsafe>" in sections[0].get_text() and "<unsafe>" not in str(sections[0])
    assert len(sections[0].select("p")) == 2
    assert not sections[0].select("figure") and not sections[1].select("figure")
    assert [image["src"] for image in sections[2].select("figure img")] == ["../media/ambulance.jpg", "../media/second.jpg"]
    assert all(figure.find_parent("section") is sections[2] for figure in sections[2].select("figure"))
    assert soup.select_one('.article-sources a[href="https://example.com/source"]')
    assert soup.select_one(".article-sources h2").get_text() == "Sources used in this article"
    visible = soup.get_text(" ", strip=True)
    for hidden in ("Claim boundary", "Supported", "Not claimed", "The club promised changes.", "internal purpose one", "Package headline", "Package Korean receipt"):
        assert hidden not in visible
    assert not soup.html and not soup.head and not soup.body and not soup.main and not soup.header
    supplied = _package(hero_media={"path": "hero.jpg", "caption": "Hero", "credit": "Desk", "source_url": "", "rights_status": "supplied"})
    assert "hero.jpg" not in render_article_package(ArticlePackage.model_validate(supplied))


@pytest.mark.parametrize(("payload", "message"), [
    ({"not": "a package"}, "Invalid ArticlePackage"), (_package(issue_id="wrong"), "issue_id mismatch"), (_package(editorial_slot="card_99"), "has no EditorialCard"),
])
def test_invalid_publication_inputs_fail_clearly(tmp_path: Path, payload: object, message: str) -> None:
    _write_package(tmp_path, payload)
    with pytest.raises(ValueError, match=message): issue_builder.render_issue([_signal(i) for i in range(1, 5)], ISSUE, tmp_path)


def test_duplicate_package_slugs_fail(tmp_path: Path) -> None:
    _write_package(tmp_path, _package(), "one.json"); _write_package(tmp_path, _package(), "two.json")
    with pytest.raises(ValueError, match="Duplicate ArticlePackage"): issue_builder.render_issue([_signal(i) for i in range(1, 5)], ISSUE, tmp_path)


def test_no_package_directory_keeps_legacy_wrapper_behavior(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    articles = tmp_path / "articles"; articles.mkdir(); target = articles / "card_01.html"; calls = []
    def legacy(editorial, issue, issue_dir):
        calls.append("legacy"); target.write_text("<html><body>legacy</body></html>", encoding="utf-8"); return "result"
    monkeypatch.setitem(issue_builder._write_articles.__globals__, "_owa", legacy)
    assert issue_builder._write_articles([], ISSUE, tmp_path) == "result" and calls == ["legacy"]
    assert "legacy" in target.read_text(encoding="utf-8") and 'class="site-footer"' in target.read_text(encoding="utf-8")


def test_missing_legacy_insertion_anchor_fails_clearly(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    articles = tmp_path / "articles"; articles.mkdir(); target = articles / "card_02.html"
    card = type("Card", (), {"article_slug": "card_02"})()
    monkeypatch.setitem(issue_builder._write_articles.__globals__, "_owa", lambda *args: target.write_text("<html>legacy without anchor</html>", encoding="utf-8"))
    monkeypatch.setitem(issue_builder._write_articles.__globals__, "_load_article_packages", lambda *args: [(ArticlePackage.model_validate(_package()), card)])
    with pytest.raises(ValueError, match="insertion anchor missing for stadium-response"): issue_builder._write_articles([card], ISSUE, tmp_path)


def test_public_render_augments_legacy_article_and_stabilization_preserves_it(tmp_path: Path) -> None:
    baseline, rich = tmp_path / "baseline", tmp_path / "rich"
    cards = [_signal(i) for i in range(1, 5)]
    issue_builder.render_issue(cards, ISSUE, baseline)
    _write_package(rich, _package())
    newsletter, brief = issue_builder.render_issue(cards, ISSUE, rich)
    assert newsletter.is_file() and brief.is_file()
    article_dir = rich / ISSUE / "articles"
    card_02 = (article_dir / "stadium-response.html").read_text(encoding="utf-8")
    soup = BeautifulSoup(card_02, "html.parser")
    assert soup.select_one("section.translation div:first-child h2").get_text() == "Korean"
    assert soup.select_one('section.translation div:first-child p[lang="ko"]').get_text() == "Legacy Korean 2"
    assert soup.select_one("section.translation div:nth-child(2) h2").get_text() == "In English"
    assert soup.select_one("section.translation div:nth-child(2) p").get_text() == "Legacy English 2"
    assert "What the Internet Is Really Saying" in card_02
    assert card_02.index("What the Internet Is Really Saying") < card_02.index('class="article-depth"') < card_02.index("Context & receipts")
    assert ".article-depth{border-top:1px solid var(--line)" in card_02
    assert "font:700 24px/1.2 Georgia,serif" in card_02
    assert "font-size:21px" in card_02
    assert all(section["heading"] in card_02 for section in _package()["sections"])
    assert card_02.index("First depth heading") < card_02.index("Second depth heading") < card_02.index("Third depth heading") < card_02.index("../media/ambulance.jpg")
    visible = soup.get_text(" ", strip=True)
    for hidden in ("Claim boundary", "Supported", "Not claimed", "The club promised changes.", "internal purpose one"):
        assert hidden not in visible
    assert "Sources used in this article" in visible and "Context & receipts" in visible
    assert soup.select_one(".article-head h1").get_text() == "Signal 2"
    assert soup.select_one(".hero") is None  # fixture has no enriched hero; package hero does not create one
    assert soup.select_one(".comment-capture form[name=ksignal-comment]")
    assert soup.select_one("footer.site-footer")
    baseline_02 = (baseline / ISSUE / "articles" / "card_02.html").read_text(encoding="utf-8")
    baseline_soup = BeautifulSoup(baseline_02, "html.parser")
    anchor = "<section><h2>Context & receipts</h2>"
    for selector in (".article-head", ".hero", "section.translation"):
        assert str(soup.select_one(selector)) == str(baseline_soup.select_one(selector))
    projected_tail = card_02[card_02.index(anchor):].replace(
        "articles/stadium-response.html", "articles/card_02.html"
    )
    assert projected_tail == baseline_02[baseline_02.index(anchor):]
    for slug in ("card_01", "card_03", "card_04"):
        current = (article_dir / f"{slug}.html").read_bytes()
        legacy = (baseline / ISSUE / "articles" / f"{slug}.html").read_bytes()
        assert current.replace(b"stadium-response.html", b"card_02.html") == legacy
        assert b"article-package" not in current
    assert 'articles/stadium-response.html' in newsletter.read_text(encoding="utf-8")
    assert not (article_dir / "card_02.html").exists()
    issue_builder.render_issue(cards, ISSUE, rich)
    assert (article_dir / "stadium-response.html").is_file()
    assert not (article_dir / "card_02.html").exists()
