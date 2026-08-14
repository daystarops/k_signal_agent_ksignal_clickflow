from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Callable, Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field


GOOGLE_TRENDS_KR_RSS_URL = "https://trends.google.com/trending/rss?geo=KR"
GOOGLE_TRENDS_NAMESPACE = "https://trends.google.com/trending/rss"
NEWSIS_FEEDS = (
    ("society", "https://www.newsis.com/RSS/society.xml"),
    ("sports", "https://www.newsis.com/RSS/sports.xml"),
    ("entertain", "https://www.newsis.com/RSS/entertain.xml"),
)
YOUTUBE_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
_TIMEOUT_SECONDS = 20.0


class _FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class GoogleContextRef(_FrozenModel):
    title: str
    source: str
    url: str


class GoogleWakeCandidate(_FrozenModel):
    query: str
    provider: Literal["google_trends_rss"] = "google_trends_rss"
    geo: Literal["KR"] = "KR"
    observed_at: datetime
    approx_traffic_raw: str
    approx_traffic_floor: int = Field(ge=0)
    context_refs: tuple[GoogleContextRef, ...] = ()


class GoogleWakeCollection(_FrozenModel):
    started_at: datetime
    completed_at: datetime
    items: tuple[GoogleWakeCandidate, ...]


class NewsisItem(_FrozenModel):
    feed: Literal["society", "sports", "entertain"]
    title: str
    description: str
    url: str
    published_at: datetime | None
    published_at_raw: str


class NewsisCollection(_FrozenModel):
    started_at: datetime
    completed_at: datetime
    items: tuple[NewsisItem, ...]


class YouTubeItem(_FrozenModel):
    video_id: str
    channel_id: str
    channel_title: str
    title: str
    description: str
    published_at: datetime
    published_at_raw: str
    url: str


class YouTubeCollection(_FrozenModel):
    started_at: datetime
    completed_at: datetime
    items: tuple[YouTubeItem, ...]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _text(element: ET.Element | None) -> str:
    return "" if element is None or element.text is None else element.text.strip()


def _parse_rss_datetime(raw: str) -> datetime:
    parsed = parsedate_to_datetime(raw)
    if parsed.tzinfo is None:
        raise ValueError("RSS timestamp must include a timezone")
    return parsed.astimezone(timezone.utc)


def _parse_rfc3339_datetime(raw: str) -> datetime:
    parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include a timezone")
    return parsed.astimezone(timezone.utc)


def _traffic_floor(raw: str) -> int:
    if not re.fullmatch(r"[\d,]+\+", raw):
        raise ValueError(f"invalid Google Trends traffic magnitude: {raw!r}")
    digits = raw[:-1].replace(",", "")
    if not digits.isdigit():
        raise ValueError(f"invalid Google Trends traffic magnitude: {raw!r}")
    return int(digits)


def parse_google_trends_rss(xml: str) -> tuple[GoogleWakeCandidate, ...]:
    root = ET.fromstring(xml)
    namespace = {"ht": GOOGLE_TRENDS_NAMESPACE}
    candidates: list[GoogleWakeCandidate] = []
    for item in root.findall("./channel/item"):
        query = _text(item.find("title"))
        traffic_raw = _text(item.find("ht:approx_traffic", namespace))
        observed_at_raw = _text(item.find("pubDate"))
        context_refs = tuple(
            GoogleContextRef(
                title=_text(news_item.find("ht:news_item_title", namespace)),
                source=_text(news_item.find("ht:news_item_source", namespace)),
                url=_text(news_item.find("ht:news_item_url", namespace)),
            )
            for news_item in item.findall("ht:news_item", namespace)
        )
        candidates.append(
            GoogleWakeCandidate(
                query=query,
                observed_at=_parse_rss_datetime(observed_at_raw),
                approx_traffic_raw=traffic_raw,
                approx_traffic_floor=_traffic_floor(traffic_raw),
                context_refs=context_refs,
            )
        )
    return tuple(candidates)


def parse_newsis_rss(
    xml: str, feed: Literal["society", "sports", "entertain"]
) -> tuple[NewsisItem, ...]:
    root = ET.fromstring(xml)
    items: list[NewsisItem] = []
    for item in root.findall("./channel/item"):
        published_at_raw = _text(item.find("pubDate"))
        try:
            published_at = _parse_rss_datetime(published_at_raw) if published_at_raw else None
        except (TypeError, ValueError, OverflowError):
            published_at = None
        items.append(
            NewsisItem(
                feed=feed,
                title=_text(item.find("title")),
                description=_text(item.find("description")),
                url=_text(item.find("link")),
                published_at=published_at,
                published_at_raw=published_at_raw,
            )
        )
    return tuple(items)


def _with_client(client: httpx.Client | None, operation: Callable[[httpx.Client], object]):
    if client is not None:
        return operation(client)
    with httpx.Client(timeout=_TIMEOUT_SECONDS) as owned_client:
        return operation(owned_client)


def collect_google_trends_kr(client: httpx.Client | None = None) -> GoogleWakeCollection:
    started_at = _utcnow()

    def operation(active_client: httpx.Client) -> tuple[GoogleWakeCandidate, ...]:
        response = active_client.get(GOOGLE_TRENDS_KR_RSS_URL, timeout=_TIMEOUT_SECONDS)
        response.raise_for_status()
        return parse_google_trends_rss(response.text)

    items = _with_client(client, operation)
    return GoogleWakeCollection(started_at=started_at, completed_at=_utcnow(), items=items)


def collect_newsis_pool(client: httpx.Client | None = None) -> NewsisCollection:
    started_at = _utcnow()

    def operation(active_client: httpx.Client) -> tuple[NewsisItem, ...]:
        items: list[NewsisItem] = []
        for feed, url in NEWSIS_FEEDS:
            response = active_client.get(url, timeout=_TIMEOUT_SECONDS)
            response.raise_for_status()
            items.extend(parse_newsis_rss(response.text, feed))
        return tuple(items)

    items = _with_client(client, operation)
    return NewsisCollection(started_at=started_at, completed_at=_utcnow(), items=items)


def collect_youtube_search(
    query: str,
    published_after: datetime,
    api_key: str,
    client: httpx.Client | None = None,
) -> YouTubeCollection:
    if published_after.tzinfo is None:
        raise ValueError("published_after must be timezone-aware")
    published_after_utc = published_after.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    params = {
        "part": "snippet",
        "type": "video",
        "regionCode": "KR",
        "relevanceLanguage": "ko",
        "order": "date",
        "maxResults": 5,
        "publishedAfter": published_after_utc,
        "q": query,
        "key": api_key,
    }
    started_at = _utcnow()

    def operation(active_client: httpx.Client) -> tuple[YouTubeItem, ...]:
        request_failed = False
        try:
            response = active_client.get(YOUTUBE_SEARCH_URL, params=params, timeout=_TIMEOUT_SECONDS)
            response.raise_for_status()
        except (httpx.HTTPStatusError, httpx.RequestError):
            request_failed = True
        if request_failed:
            raise RuntimeError("YouTube request failed") from None

        normalized: list[YouTubeItem] = []
        for item in response.json()["items"]:
            video_id = item["id"]["videoId"]
            snippet = item["snippet"]
            published_at_raw = snippet["publishedAt"]
            normalized.append(
                YouTubeItem(
                    video_id=video_id,
                    channel_id=snippet["channelId"],
                    channel_title=snippet["channelTitle"],
                    title=snippet["title"],
                    description=snippet["description"],
                    published_at=_parse_rfc3339_datetime(published_at_raw),
                    published_at_raw=published_at_raw,
                    url=f"https://www.youtube.com/watch?v={video_id}",
                )
            )
        return tuple(normalized)

    items = _with_client(client, operation)
    return YouTubeCollection(started_at=started_at, completed_at=_utcnow(), items=items)
