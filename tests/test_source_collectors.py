from datetime import datetime, timezone

import httpx
import pytest

from ksignal.engine.source_collectors import (
    GOOGLE_TRENDS_KR_RSS_URL,
    NEWSIS_FEEDS,
    YOUTUBE_SEARCH_URL,
    GoogleWakeCandidate,
    collect_google_trends_kr,
    collect_newsis_pool,
    collect_youtube_search,
    parse_google_trends_rss,
)


GOOGLE_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss xmlns:ht="https://trends.google.com/trending/rss"><channel>
  <item><title> 임지민 </title><ht:approx_traffic>1000+</ht:approx_traffic>
    <pubDate>Fri, 14 Aug 2026 14:00:00 +0000</pubDate>
    <ht:news_item><ht:news_item_title> 문맥 제목 </ht:news_item_title>
      <ht:news_item_url>https://context.invalid/one</ht:news_item_url>
      <ht:news_item_source> 문맥 출처 </ht:news_item_source></ht:news_item>
    <ht:news_item><ht:news_item_title>두 번째</ht:news_item_title>
      <ht:news_item_url>https://context.invalid/two</ht:news_item_url>
      <ht:news_item_source>둘째 출처</ht:news_item_source></ht:news_item>
  </item>
  <item><title>쉼표</title><ht:approx_traffic>2,000+</ht:approx_traffic>
    <pubDate>Fri, 14 Aug 2026 14:05:00 +0000</pubDate></item>
</channel></rss>"""


def newsis_rss(items: list[tuple[str, str, str]]) -> str:
    body = "".join(
        f"<item><title>{title}</title><description>설명</description><link>{url}</link>"
        f"<pubDate>{published}</pubDate></item>"
        for title, url, published in items
    )
    return f"<rss><channel>{body}</channel></rss>"


YOUTUBE_IDS = ("0lFRsI7OvVk", "j9EEd9SQMxY", "iosYCnw5HaY", "xq8eOiiucBI", "dlvgSpzutK4")
DECOMPOSED_TITLE = "임지민 선수"


class FakeClient:
    def __init__(self, handler):
        self.handler = handler
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.handler(url, kwargs)


def response(*, text=None, json=None):
    request = httpx.Request("GET", "https://example.test")
    if json is not None:
        return httpx.Response(200, json=json, request=request)
    return httpx.Response(200, text=text or "", request=request)


def test_google_parser_preserves_order_context_and_magnitude_semantics():
    wakes = parse_google_trends_rss(GOOGLE_RSS)
    assert wakes[0].query == "임지민"
    assert wakes[0].approx_traffic_raw == "1000+"
    assert wakes[0].approx_traffic_floor == 1000
    assert wakes[0].observed_at == datetime(2026, 8, 14, 14, tzinfo=timezone.utc)
    assert [(ref.title, ref.source, ref.url) for ref in wakes[0].context_refs] == [
        ("문맥 제목", "문맥 출처", "https://context.invalid/one"),
        ("두 번째", "둘째 출처", "https://context.invalid/two"),
    ]
    assert wakes[1].approx_traffic_floor == 2000
    assert wakes[1].context_refs == ()


def test_google_invalid_traffic_fails_explicitly():
    with pytest.raises(ValueError, match="traffic magnitude"):
        parse_google_trends_rss(GOOGLE_RSS.replace("1000+", "about 1000"))


def test_google_wake_candidate_rejects_negative_traffic_floor():
    with pytest.raises(ValueError):
        GoogleWakeCandidate(
            query="test",
            observed_at=datetime(2026, 8, 14, tzinfo=timezone.utc),
            approx_traffic_raw="-1",
            approx_traffic_floor=-1,
        )


def test_google_collection_fetches_only_the_feed_not_context_urls():
    client = FakeClient(lambda url, kwargs: response(text=GOOGLE_RSS))
    result = collect_google_trends_kr(client)
    assert [call[0] for call in client.calls] == [GOOGLE_TRENDS_KR_RSS_URL]
    assert result.started_at.tzinfo is not None
    assert result.completed_at >= result.started_at


def test_newsis_fixed_pool_returns_all_items_and_normalizes_valid_timestamp():
    game_url = "https://www.newsis.com/view/NISX20260814_0003750254"
    injury_url = "https://www.newsis.com/view/NISX20260814_0003750360"
    feeds = {
        NEWSIS_FEEDS[0][1]: newsis_rss([("사회 기사", "https://www.newsis.com/social", "bad date")]),
        NEWSIS_FEEDS[1][1]: newsis_rss(
            [
                ("[KBO 오늘의 경기 결과]8월14일(금)", game_url, "Fri, 14 Aug 2026 23:10:00 +0900"),
                ("강습 타구에 얼굴 강타당한 NC 임지민, 구급차로 병원 이송", injury_url, "Fri, 14 Aug 2026 23:18:35 +0900"),
            ]
        ),
        NEWSIS_FEEDS[2][1]: newsis_rss([]),
    }
    client = FakeClient(lambda url, kwargs: response(text=feeds[url]))
    result = collect_newsis_pool(client)
    assert [call[0] for call in client.calls] == [url for _, url in NEWSIS_FEEDS]
    assert len(set(call[0] for call in client.calls)) == 3
    assert [item.url for item in result.items if item.url in {game_url, injury_url}] == [
        game_url,
        injury_url,
    ]
    injury = next(item for item in result.items if item.url == injury_url)
    assert injury.feed == "sports"
    assert injury.published_at_raw == "Fri, 14 Aug 2026 23:18:35 +0900"
    assert injury.published_at == datetime(2026, 8, 14, 14, 18, 35, tzinfo=timezone.utc)
    assert result.items[0].published_at is None
    assert all(call[0] not in {game_url, injury_url} for call in client.calls)


def test_youtube_exact_bounded_request_and_normalized_order():
    titles = (
        "임지민 선수의 쾌유를 기원합니다.",
        "임지민 선수 큰 부상이 아니길 기도합니다",
        "임지민 안면을 강타한 타구",
        DECOMPOSED_TITLE,
        "260814_NC 임지민 안면 강타",
    )
    payload = {
        "items": [
            {
                "id": {"videoId": video_id},
                "snippet": {
                    "channelId": f"channel-{index}",
                    "channelTitle": "NC다이노스" if index == 1 else f"채널 {index}",
                    "title": titles[index],
                    "description": "설명",
                    "publishedAt": f"2026-08-14T15:0{4-index}:02Z",
                },
            }
            for index, video_id in enumerate(YOUTUBE_IDS)
        ]
    }
    client = FakeClient(lambda url, kwargs: response(json=payload))
    lower_bound = datetime(2026, 8, 14, 14, tzinfo=timezone.utc)
    result = collect_youtube_search("임지민", lower_bound, "secret-api-key", client)

    assert len(client.calls) == 1
    url, kwargs = client.calls[0]
    assert url == YOUTUBE_SEARCH_URL
    assert kwargs["params"] == {
        "part": "snippet",
        "type": "video",
        "regionCode": "KR",
        "relevanceLanguage": "ko",
        "order": "date",
        "maxResults": 5,
        "publishedAfter": "2026-08-14T14:00:00Z",
        "q": "임지민",
        "key": "secret-api-key",
    }
    assert tuple(item.video_id for item in result.items) == YOUTUBE_IDS
    assert result.items[1].channel_id == "channel-1"
    assert result.items[1].channel_title == "NC다이노스"
    assert result.items[3].title == DECOMPOSED_TITLE
    assert result.items[0].url == "https://www.youtube.com/watch?v=0lFRsI7OvVk"
    assert "secret-api-key" not in result.model_dump_json()
    assert [call[0] for call in client.calls] == [YOUTUBE_SEARCH_URL]
    assert result.completed_at >= result.started_at


def test_youtube_http_error_does_not_expose_api_key():
    request = httpx.Request(
        "GET", f"{YOUTUBE_SEARCH_URL}?key=secret-api-key"
    )
    client = FakeClient(
        lambda url, kwargs: httpx.Response(403, request=request)
    )

    with pytest.raises(RuntimeError) as exc_info:
        collect_youtube_search(
            "test", datetime(2026, 8, 14, tzinfo=timezone.utc), "secret-api-key", client
        )

    assert "secret-api-key" not in str(exc_info.value)
    assert exc_info.value.__context__ is None


def test_youtube_transport_error_does_not_expose_api_key():
    request = httpx.Request(
        "GET", f"{YOUTUBE_SEARCH_URL}?key=secret-api-key"
    )

    def raise_transport_error(url, kwargs):
        raise httpx.ConnectError("connection failed", request=request)

    client = FakeClient(raise_transport_error)

    with pytest.raises(RuntimeError) as exc_info:
        collect_youtube_search(
            "test", datetime(2026, 8, 14, tzinfo=timezone.utc), "secret-api-key", client
        )

    assert "secret-api-key" not in str(exc_info.value)
    assert exc_info.value.__context__ is None


def test_collectors_do_not_construct_downstream_evidence_types():
    import ksignal.engine.source_collectors as collectors

    assert not hasattr(collectors, "EvidencePacket")
    assert not hasattr(collectors, "EvidenceAssessment")
