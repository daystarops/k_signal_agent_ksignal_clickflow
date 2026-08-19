"""Provider-neutral media acquisition and normalization.

This module discovers candidates only. It does not rank media, decide whether a
license is compatible with a use, download assets, or write a media manifest.

Editorial ranking contract for the later orchestration layer: when a relevant,
provenance-sound, rights-compatible video substantially better captures or
explains the subject than available still imagery, K-Signal should prefer the
video as primary media. Photographs/stills may then provide supporting context.
Video does not win merely because video exists.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable, Literal

import httpx
from pydantic import BaseModel, ConfigDict


YOUTUBE_VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"
YOUTUBE_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
WIKIMEDIA_API_URL = "https://commons.wikimedia.org/w/api.php"
OPENVERSE_IMAGES_URL = "https://api.openverse.org/v1/images/"
WIKIMEDIA_USER_AGENT = "K-Signal/0.1 (media acquisition; public API client)"
_TIMEOUT_SECONDS = 20.0
_YOUTUBE_BATCH_SIZE = 50


class _FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class MediaCandidate(_FrozenModel):
    provider: Literal["youtube", "wikimedia_commons", "openverse"]
    provider_asset_id: str
    media_type: Literal["image", "video"]
    title: str | None
    description: str | None = None
    published_at: datetime | None = None
    creator: str | None = None
    source: str | None = None
    media_url: str
    landing_url: str
    thumbnail_url: str | None = None
    embed_url: str | None = None
    license_code: str | None = None
    license_version: str | None = None
    license_url: str | None = None
    rights_statement: str | None = None
    usage_terms: str | None = None
    width: int | None = None
    height: int | None = None
    embeddable: bool | None = None
    duration_iso8601: str | None = None


class MediaAcquisitionResult(_FrozenModel):
    started_at: datetime
    completed_at: datetime
    candidates: tuple[MediaCandidate, ...]
    missing_asset_ids: tuple[str, ...] = ()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _with_client(client: httpx.Client | None, operation: Callable[[httpx.Client], object]):
    if client is not None:
        return operation(client)
    with httpx.Client(timeout=_TIMEOUT_SECONDS) as owned_client:
        return operation(owned_client)


def _bounded_count(result_count: int, maximum: int) -> int:
    if isinstance(result_count, bool) or not 1 <= result_count <= maximum:
        raise ValueError(f"result_count must be between 1 and {maximum}")
    return result_count


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_int(value: object) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_datetime(value: object) -> datetime | None:
    text = _optional_text(value)
    if text is None:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _youtube_thumbnail(snippet: dict) -> tuple[str | None, int | None, int | None]:
    thumbnails = snippet.get("thumbnails") or {}
    for name in ("maxres", "standard", "high", "medium", "default"):
        thumbnail = thumbnails.get(name)
        if isinstance(thumbnail, dict) and _optional_text(thumbnail.get("url")):
            return (
                _optional_text(thumbnail.get("url")),
                _optional_int(thumbnail.get("width")),
                _optional_int(thumbnail.get("height")),
            )
    return None, None, None


def collect_youtube_media(
    video_ids: tuple[str, ...],
    api_key: str,
    client: httpx.Client | None = None,
) -> MediaAcquisitionResult:
    """Enrich arbitrary YouTube IDs without downloading video content."""
    if any(not isinstance(video_id, str) or not video_id.strip() for video_id in video_ids):
        raise ValueError("video_ids must contain non-empty strings")
    ordered_ids = tuple(dict.fromkeys(video_ids))
    started_at = _utcnow()

    def operation(active_client: httpx.Client) -> tuple[tuple[MediaCandidate, ...], tuple[str, ...]]:
        payloads: dict[str, dict] = {}
        for offset in range(0, len(ordered_ids), _YOUTUBE_BATCH_SIZE):
            batch = ordered_ids[offset : offset + _YOUTUBE_BATCH_SIZE]
            params = {
                "part": "snippet,status,contentDetails",
                "id": ",".join(batch),
                "key": api_key,
            }
            request_failed = False
            try:
                response = active_client.get(
                    YOUTUBE_VIDEOS_URL, params=params, timeout=_TIMEOUT_SECONDS
                )
                response.raise_for_status()
            except (httpx.HTTPStatusError, httpx.RequestError):
                request_failed = True
            if request_failed:
                raise RuntimeError("YouTube media request failed") from None
            body = response.json()
            if not isinstance(body, dict) or not isinstance(body.get("items"), list):
                raise ValueError("malformed YouTube media response")
            for item in body["items"]:
                if not isinstance(item, dict) or not _optional_text(item.get("id")):
                    raise ValueError("malformed YouTube media item")
                payloads[str(item["id"])] = item

        candidates: list[MediaCandidate] = []
        missing: list[str] = []
        for video_id in ordered_ids:
            item = payloads.get(video_id)
            if item is None:
                missing.append(video_id)
                continue
            snippet = item.get("snippet")
            status = item.get("status")
            details = item.get("contentDetails") or {}
            if not isinstance(snippet, dict) or not isinstance(status, dict):
                raise ValueError(f"malformed YouTube media item: {video_id}")
            title = _optional_text(snippet.get("title"))
            channel_title = _optional_text(snippet.get("channelTitle"))
            if title is None or channel_title is None or not isinstance(status.get("embeddable"), bool):
                raise ValueError(f"malformed YouTube media item: {video_id}")
            thumbnail_url, width, height = _youtube_thumbnail(snippet)
            embeddable = status["embeddable"]
            watch_url = f"https://www.youtube.com/watch?v={video_id}"
            candidates.append(
                MediaCandidate(
                    provider="youtube",
                    provider_asset_id=video_id,
                    media_type="video",
                    title=title,
                    description=_optional_text(snippet.get("description")),
                    published_at=_optional_datetime(snippet.get("publishedAt")),
                    creator=channel_title,
                    source=_optional_text(snippet.get("channelId")),
                    media_url=watch_url,
                    landing_url=watch_url,
                    thumbnail_url=thumbnail_url,
                    embed_url=f"https://www.youtube.com/embed/{video_id}" if embeddable else None,
                    license_code=_optional_text(status.get("license")),
                    width=width,
                    height=height,
                    embeddable=embeddable,
                    duration_iso8601=_optional_text(details.get("duration")),
                )
            )
        return tuple(candidates), tuple(missing)

    candidates, missing = _with_client(client, operation) if ordered_ids else ((), ())
    return MediaAcquisitionResult(
        started_at=started_at,
        completed_at=_utcnow(),
        candidates=candidates,
        missing_asset_ids=missing,
    )


def search_youtube_media(
    query: str,
    api_key: str,
    result_count: int = 10,
    client: httpx.Client | None = None,
) -> MediaAcquisitionResult:
    """Discover editorial YouTube candidates by relevance, then enrich their IDs."""
    count = _bounded_count(result_count, 50)
    if not query.strip():
        raise ValueError("query must not be empty")

    def operation(active_client: httpx.Client) -> MediaAcquisitionResult:
        params = {
            "part": "snippet",
            "q": query,
            "type": "video",
            "order": "relevance",
            "maxResults": count,
            "regionCode": "KR",
            "relevanceLanguage": "ko",
            "key": api_key,
        }
        request_failed = False
        try:
            response = active_client.get(
                YOUTUBE_SEARCH_URL, params=params, timeout=_TIMEOUT_SECONDS
            )
            response.raise_for_status()
        except (httpx.HTTPStatusError, httpx.RequestError):
            request_failed = True
        if request_failed:
            raise RuntimeError("YouTube media search request failed") from None
        body = response.json()
        if not isinstance(body, dict) or not isinstance(body.get("items"), list):
            raise ValueError("malformed YouTube media search response")
        video_ids: list[str] = []
        for item in body["items"]:
            if not isinstance(item, dict) or not isinstance(item.get("id"), dict):
                raise ValueError("malformed YouTube media search item")
            video_id = _optional_text(item["id"].get("videoId"))
            if video_id is None:
                raise ValueError("malformed YouTube media search item")
            video_ids.append(video_id)
        return collect_youtube_media(tuple(video_ids), api_key, active_client)

    return _with_client(client, operation)


def _commons_metadata(item: dict, key: str) -> str | None:
    imageinfo = (item.get("imageinfo") or [{}])[0]
    value = (imageinfo.get("extmetadata") or {}).get(key)
    return _optional_text(value.get("value")) if isinstance(value, dict) else None


def search_wikimedia_commons(
    query: str,
    result_count: int = 10,
    client: httpx.Client | None = None,
) -> MediaAcquisitionResult:
    count = _bounded_count(result_count, 50)
    if not query.strip():
        raise ValueError("query must not be empty")
    started_at = _utcnow()
    params = {
        "action": "query",
        "format": "json",
        "formatversion": 2,
        "generator": "search",
        "gsrsearch": query,
        "gsrnamespace": 6,
        "gsrlimit": count,
        "prop": "imageinfo|info",
        "iiprop": "url|mime|size|extmetadata",
        "iiextmetadatafilter": (
            "Artist|Credit|ImageDescription|DateTimeOriginal|LicenseShortName|LicenseUrl|"
            "UsageTerms|Copyrighted|Attribution"
        ),
        "inprop": "url",
    }

    def operation(active_client: httpx.Client) -> tuple[MediaCandidate, ...]:
        response = active_client.get(
            WIKIMEDIA_API_URL,
            params=params,
            headers={"User-Agent": WIKIMEDIA_USER_AGENT},
            timeout=_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        pages = (response.json().get("query") or {}).get("pages") or []
        candidates: list[MediaCandidate] = []
        for page in pages:
            imageinfo = (page.get("imageinfo") or [None])[0]
            if not isinstance(imageinfo, dict) or not _optional_text(imageinfo.get("url")):
                continue
            mime = _optional_text(imageinfo.get("mime")) or ""
            if mime.startswith("image/"):
                media_type = "image"
            elif mime.startswith("video/"):
                media_type = "video"
            else:
                continue
            page_id = _optional_text(page.get("pageid")) or _optional_text(page.get("title"))
            title = _optional_text(page.get("title"))
            landing_url = _optional_text(page.get("canonicalurl")) or _optional_text(
                imageinfo.get("descriptionurl")
            )
            if page_id is None or title is None or landing_url is None:
                continue
            candidates.append(
                MediaCandidate(
                    provider="wikimedia_commons",
                    provider_asset_id=page_id,
                    media_type=media_type,
                    title=title.removeprefix("File:"),
                    description=_commons_metadata(page, "ImageDescription"),
                    published_at=_optional_datetime(_commons_metadata(page, "DateTimeOriginal")),
                    creator=_commons_metadata(page, "Artist"),
                    source=_commons_metadata(page, "Credit"),
                    media_url=str(imageinfo["url"]),
                    landing_url=landing_url,
                    thumbnail_url=_optional_text(imageinfo.get("thumburl")),
                    license_code=_commons_metadata(page, "LicenseShortName"),
                    license_url=_commons_metadata(page, "LicenseUrl"),
                    rights_statement=_commons_metadata(page, "Copyrighted"),
                    usage_terms=_commons_metadata(page, "UsageTerms")
                    or _commons_metadata(page, "Attribution"),
                    width=_optional_int(imageinfo.get("width")),
                    height=_optional_int(imageinfo.get("height")),
                )
            )
        return tuple(candidates)

    candidates = _with_client(client, operation)
    return MediaAcquisitionResult(
        started_at=started_at, completed_at=_utcnow(), candidates=candidates
    )


def search_openverse(
    query: str,
    result_count: int = 10,
    client: httpx.Client | None = None,
) -> MediaAcquisitionResult:
    count = _bounded_count(result_count, 20)
    if not query.strip():
        raise ValueError("query must not be empty")
    started_at = _utcnow()
    params = {"q": query, "page_size": count}

    def operation(active_client: httpx.Client) -> tuple[MediaCandidate, ...]:
        response = active_client.get(OPENVERSE_IMAGES_URL, params=params, timeout=_TIMEOUT_SECONDS)
        response.raise_for_status()
        results = response.json().get("results") or []
        candidates: list[MediaCandidate] = []
        for item in results:
            asset_id = _optional_text(item.get("id"))
            media_url = _optional_text(item.get("url"))
            landing_url = _optional_text(item.get("foreign_landing_url"))
            if asset_id is None or media_url is None or landing_url is None:
                continue
            candidates.append(
                MediaCandidate(
                    provider="openverse",
                    provider_asset_id=asset_id,
                    media_type="image",
                    title=_optional_text(item.get("title")),
                    description=_optional_text(item.get("description")),
                    published_at=_optional_datetime(item.get("created_on")),
                    creator=_optional_text(item.get("creator")),
                    source=_optional_text(item.get("source")) or _optional_text(item.get("provider")),
                    media_url=media_url,
                    landing_url=landing_url,
                    thumbnail_url=_optional_text(item.get("thumbnail")),
                    license_code=_optional_text(item.get("license")),
                    license_version=_optional_text(item.get("license_version")),
                    license_url=_optional_text(item.get("license_url")),
                    width=_optional_int(item.get("width")),
                    height=_optional_int(item.get("height")),
                )
            )
        return tuple(candidates)

    candidates = _with_client(client, operation)
    return MediaAcquisitionResult(
        started_at=started_at, completed_at=_utcnow(), candidates=candidates
    )
