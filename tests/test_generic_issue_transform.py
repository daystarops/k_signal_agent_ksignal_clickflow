from __future__ import annotations

from pathlib import Path
import json

import pytest

import ksignal.issue_builder as issue_builder
from ksignal.schema import SignalCard


def _card(**changes: object) -> SignalCard:
    values = {
        "source": "테스트 소스",
        "url": "https://example.kr/signals/new-story",
        "category": "consumer_trends",
        "title_original": "한국어 원제",
        "title_english": "A New Signal",
        "raw_korean_excerpt": "사람들이 새로운 흐름에 주목하고 있다.",
        "literal_translation": "People are paying attention to a new current.",
        "cultural_read": "This is spreading because it gives an old habit a new social meaning.",
        "business_read": "Retailers can test demand through limited releases.",
        "tags": ["새로운", "흐름"],
    }
    values.update(changes)
    return SignalCard(**values)


def test_generic_transform_preserves_contract_and_omits_comments() -> None:
    card = _card(
        title_english="T" * (issue_builder.LIMITS["title"] + 10),
        literal_translation="번역 " * 100,
        cultural_read="문화적 맥락 " * 100,
        business_read="사업적 의미 " * 100,
    )

    editorial = issue_builder.transform_card(card)

    assert editorial.title == issue_builder._compact(card.title_english, issue_builder.LIMITS["title"])
    assert editorial.heard_in_feed == issue_builder._compact(card.cultural_read, issue_builder.LIMITS["heard"])
    assert editorial.english_translation == issue_builder._compact(card.literal_translation, issue_builder.LIMITS["english"])
    assert editorial.comments_read == ""
    assert editorial.why_it_has_legs == issue_builder._compact(card.business_read, issue_builder.LIMITS["legs"])
    assert editorial.korean_quote == issue_builder._compact(card.raw_korean_excerpt, issue_builder.LIMITS["korean"])
    assert editorial.lane == "consumer trends"
    assert editorial.watch_next == ["새로운", "흐름", "반응", "맥락", "다음"]
    assert issue_builder.validate_editorial_card(editorial, require_media=False) == []


@pytest.mark.parametrize(
    ("changes", "expected_title", "expected_lane", "expected_legs"),
    [
        ({"category": "idols"}, "A New Signal", "fandom", "Retailers can test demand through limited releases."),
        ({"title_english": "", "business_read": ""}, "한국어 원제", "consumer trends", ""),
    ],
)
def test_generic_transform_keeps_title_lane_and_business_behavior(
    changes: dict[str, object], expected_title: str, expected_lane: str, expected_legs: str
) -> None:
    editorial = issue_builder.transform_card(_card(**changes))

    assert editorial.title == expected_title
    assert editorial.lane == expected_lane
    assert editorial.why_it_has_legs == expected_legs


def test_historical_editorial_override_is_unchanged() -> None:
    override_key, override = next(iter(issue_builder.EDITORIAL_OVERRIDES.items()))
    editorial = issue_builder.transform_card(_card(url=f"https://example.kr/archive/{override_key}"))

    for field, expected in override.items():
        assert getattr(editorial, field) == expected


def test_normal_import_wires_corrected_transform_into_four_card_render(tmp_path: Path) -> None:
    cards = [
        _card(
            url=f"https://example.kr/signals/{number}",
            title_english=f"Signal {number}",
            tags=[f"태그{number}", "한국"],
        )
        for number in range(1, 5)
    ]

    newsletter, brief = issue_builder.render_issue(cards, "2026-08-16", tmp_path)

    assert newsletter == tmp_path / "2026-08-16" / "newsletter.html"
    assert brief == tmp_path / "2026-08-16" / "brief.md"
    assert newsletter.is_file()
    assert brief.is_file()


def test_rebuild_wires_new_embed_without_prior_audit_or_thumbnail(tmp_path: Path) -> None:
    issue = "2026-08-16"
    cards = [_card(url=f"https://example.kr/signals/{number}") for number in range(1, 5)]
    issue_builder.render_issue(cards, issue, tmp_path)
    media_dir = tmp_path / issue / "media"
    media_dir.mkdir()
    manifest = {
        str(index): {
            "hero_image_path": "", "hero_source_url": "", "hero_credit": "Newsroom",
            "video_url": f"https://www.youtube.com/embed/video{index}",
            "video_thumbnail_path": "", "media_confidence": "high",
            "media_reason": "Direct reporting", "source_screenshot_path": "",
            "rights_status": "embed_only",
        }
        for index in range(1, 5)
    }
    (media_dir / "media_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    issue_builder.rebuild_issue(issue, tmp_path)

    rows = json.loads((tmp_path / issue / "editorial_cards.json").read_text(encoding="utf-8"))
    assert rows[0]["video_embed_url"] == "https://www.youtube.com/embed/video1"
    assert rows[0]["video_thumbnail_path"] == ""
    article = (tmp_path / issue / "articles" / "card_01.html").read_text(encoding="utf-8")
    assert 'iframe src="https://www.youtube.com/embed/video1"' in article


def test_rebuild_aborts_before_render_when_manifest_slot_is_unresolved(tmp_path: Path) -> None:
    issue = "2026-08-16"
    cards = [_card(url=f"https://example.kr/signals/{number}") for number in range(1, 5)]
    issue_builder.render_issue(cards, issue, tmp_path)
    media_dir = tmp_path / issue / "media"
    media_dir.mkdir()
    (media_dir / "media_manifest.json").write_text(
        json.dumps({str(index): {} for index in range(1, 5)}), encoding="utf-8"
    )
    newsletter_before = (tmp_path / issue / "newsletter.html").read_bytes()

    with pytest.raises(ValueError, match="Card 1 media selection is unresolved"):
        issue_builder.rebuild_issue(issue, tmp_path)

    assert (tmp_path / issue / "newsletter.html").read_bytes() == newsletter_before
