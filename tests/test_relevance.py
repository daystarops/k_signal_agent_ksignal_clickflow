from copy import deepcopy

from ksignal.relevance import enrich_card, related_signals, score_candidate


def card(card_id, **values):
    base = {
        "issue_id": "001", "card_id": card_id, "article_path": f"articles/{card_id}.html",
        "status": "published", "published_at": "2026-08-09", "editorial_order": 1,
        "lane": "Fandom", "lane_slug": "fandom", "topic_tags": [], "entity_tags": [],
        "search_keywords": [], "source_platform": "TheQoo", "source_type": "korean_native",
        "headline": card_id, "dek": card_id,
    }
    base.update(values)
    return base


def test_scoring_table_exact_values():
    current = card("current", topic_tags=["topic", "second"], entity_tags=["entity"], search_keywords=["fandom"])
    candidate = card("candidate", topic_tags=["topic", "second"], entity_tags=["entity"], search_keywords=["fandom"])
    result = score_candidate(current, candidate)
    assert result["score"] == 25 + 24 + 18 + 6 + 4 + 3 + 5
    assert "same lane +25" in result["reasons"]
    assert sum(reason.endswith("+12") for reason in result["reasons"]) == 2
    assert any(reason.endswith("+18") for reason in result["reasons"])
    assert "shared source platform +6" in result["reasons"]
    assert "shared source type +4" in result["reasons"]
    assert "same issue +3" in result["reasons"]
    assert any(reason.endswith("+5") for reason in result["reasons"])


def test_self_and_unpublished_and_routeless_are_excluded_and_top_two_returned():
    current = card("current")
    cards = [current, card("draft", status="draft"), card("held", status="held"),
             card("routeless", article_path=""), card("one"), card("two"), card("three")]
    results, explanations = related_signals(current, cards)
    assert len(results) == 2
    assert {item["card_id"] for item in results}.isdisjoint({"current", "draft", "held", "routeless"})
    assert {item["candidate_card"] for item in explanations} == {"one", "two", "three"}


def test_newer_then_same_lane_then_override_tie_breakers():
    current = card("current", lane="Fandom", lane_slug="fandom")
    older = card("older", issue_id="002", lane="Sports", lane_slug="sports", published_at="2025-01-01")
    newer_other = card("newer_other", issue_id="002", lane="Sports", lane_slug="sports", published_at="2026-01-01")
    results, _ = related_signals(current, [older, newer_other])
    assert results[0]["card_id"] == "newer_other"

    same_lane = card("same", issue_id="002", source_platform="Other", source_type="other")
    other_lane = card("other", issue_id="001", lane="Sports", lane_slug="sports", topic_tags=["x"], source_platform="Other", source_type="other")
    # Both score 25; same lane wins the third tie-breaker.
    results, _ = related_signals(current, [other_lane, same_lane])
    assert results[0]["card_id"] == "same"
    results, _ = related_signals(current, [older, newer_other], overrides={"current": {"pinned_include": ["older"]}})
    assert results[0]["card_id"] == "older"


def test_nfkc_case_whitespace_and_bilingual_alias_preserve_display_labels():
    original = card("current", topic_tags=["  Ｋ League  "], entity_tags=["빌리"], search_keywords=[" 팬덤 "])
    candidate = card("candidate", topic_tags=["k league"], entity_tags=["Billlie"], search_keywords=["FANDOM"])
    result = score_candidate(original, candidate)
    assert result["score"] >= 12 + 18 + 5
    enriched = enrich_card(deepcopy(original))
    assert enriched["topic_tags"] == ["  Ｋ League  "]
    assert enriched["entity_tags"] == ["빌리"]


def test_public_selection_has_no_private_comment_or_moderation_data():
    current = card("current")
    candidate = card("candidate", comments_read="private", moderation_data={"state": "hold"})
    results, _ = related_signals(current, [candidate])
    assert "comments_read" not in results[0]
    assert "moderation_data" not in results[0]
