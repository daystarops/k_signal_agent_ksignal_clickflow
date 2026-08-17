import pytest

from ksignal.collectors.html_collector import extract_page_text
from ksignal.schema import RawItem


PAGE_A = """<html><head><title>임지민 부상 기사</title></head>
<body><article><h1>임지민 부상 기사</h1><p>강습 타구 뒤 병원으로 이송됐다.</p></article></body></html>"""
PAGE_B = """<html><head><title>구급차 절차 개선 기사</title></head>
<body><article><h1>구급차 절차 개선 기사</h1><p>구단은 후속 절차를 개선한다고 밝혔다.</p></article></body></html>"""


def test_same_page_title_body_and_utf8_korean_succeed():
    url = "https://news.example/article-a"
    title, body, images = extract_page_text(PAGE_A, url)
    item = RawItem(
        id="a",
        source="테스트 뉴스",
        url=url,
        title=title,
        snippet=body,
        title_source_url=url,
        snippet_source_url=url,
        title_response_id="response-a",
        snippet_response_id="response-a",
    )

    assert item.title == "임지민 부상 기사"
    assert "강습 타구 뒤 병원으로 이송됐다." in item.snippet
    assert images == []


def test_title_from_page_b_cannot_be_combined_with_body_from_page_a():
    title_b, _, _ = extract_page_text(PAGE_B, "https://news.example/article-b")
    _, body_a, _ = extract_page_text(PAGE_A, "https://news.example/article-a")

    with pytest.raises(ValueError, match="same page response"):
        RawItem(
            id="mixed",
            source="테스트 뉴스",
            url="https://news.example/article-a",
            title=title_b,
            snippet=body_a,
            title_source_url="https://news.example/article-b",
            snippet_source_url="https://news.example/article-a",
            title_response_id="response-b",
            snippet_response_id="response-a",
        )


def test_partial_provenance_is_rejected():
    with pytest.raises(ValueError, match="supplied together"):
        RawItem(
            id="partial",
            source="test",
            url="https://news.example/article-a",
            title="title",
            snippet="body",
            title_source_url="https://news.example/article-a",
        )
