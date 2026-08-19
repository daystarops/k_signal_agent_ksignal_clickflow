import httpx
import pytest
from pydantic import ValidationError

import ksignal.engine.media_acquisition as acquisition
from ksignal.engine.media_acquisition import (
    OPENVERSE_IMAGES_URL,
    WIKIMEDIA_API_URL,
    YOUTUBE_VIDEOS_URL,
    YOUTUBE_SEARCH_URL,
    MediaCandidate,
    collect_youtube_media,
    search_openverse,
    search_wikimedia_commons,
    search_youtube_media,
)


class FakeClient:
    def __init__(self, handler):
        self.handler = handler
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.handler(url, kwargs)


def response(payload, status_code=200, request_url="https://example.test"):
    return httpx.Response(
        status_code, json=payload, request=httpx.Request("GET", request_url)
    )


def youtube_item(video_id, license_code="youtube", embeddable=True):
    return {
        "id": video_id,
        "snippet": {
            "title": f"Video {video_id}",
            "channelId": "channel-id",
            "channelTitle": "Channel Name",
            "description": f"Description {video_id}",
            "publishedAt": "2026-08-14T15:01:02Z",
            "thumbnails": {
                "default": {"url": "https://img.test/default.jpg", "width": 120, "height": 90},
                "high": {"url": "https://img.test/high.jpg", "width": 480, "height": 360},
                "maxres": {"url": "https://img.test/maxres.jpg", "width": 1280, "height": 720},
            },
        },
        "status": {"embeddable": embeddable, "license": license_code},
        "contentDetails": {"duration": "PT2M3S"},
    }


def test_youtube_accepts_arbitrary_ids_and_normalizes_license_embed_and_thumbnail():
    ids = ("arbitrary-A", "arbitrary-B")
    payload = {
        "items": [
            youtube_item(ids[1], "creativeCommon", False),
            youtube_item(ids[0], "youtube", True),
        ]
    }
    client = FakeClient(lambda url, kwargs: response(payload))

    result = collect_youtube_media(ids, "secret-api-key", client)

    assert len(client.calls) == 1
    url, kwargs = client.calls[0]
    assert url == YOUTUBE_VIDEOS_URL
    assert kwargs["params"] == {
        "part": "snippet,status,contentDetails",
        "id": "arbitrary-A,arbitrary-B",
        "key": "secret-api-key",
    }
    assert tuple(item.provider_asset_id for item in result.candidates) == ids
    standard, creative_commons = result.candidates
    assert standard.license_code == "youtube"
    assert standard.embeddable is True
    assert standard.landing_url == "https://www.youtube.com/watch?v=arbitrary-A"
    assert standard.embed_url == "https://www.youtube.com/embed/arbitrary-A"
    assert standard.thumbnail_url == "https://img.test/maxres.jpg"
    assert standard.description == "Description arbitrary-A"
    assert standard.published_at.isoformat() == "2026-08-14T15:01:02+00:00"
    assert (standard.width, standard.height) == (1280, 720)
    assert creative_commons.license_code == "creativeCommon"
    assert creative_commons.embeddable is False
    assert creative_commons.embed_url is None
    assert "secret-api-key" not in result.model_dump_json()


def test_youtube_batches_at_api_limit_and_reports_missing_ids():
    ids = tuple(f"video-{index}" for index in range(51))

    def handler(url, kwargs):
        requested = kwargs["params"]["id"].split(",")
        return response({"items": [youtube_item(item) for item in requested if item != "video-3"]})

    client = FakeClient(handler)
    result = collect_youtube_media(ids, "key", client)
    assert len(client.calls) == 2
    assert result.missing_asset_ids == ("video-3",)
    assert len(result.candidates) == 50


@pytest.mark.parametrize("payload", [{}, {"items": [{}]}, {"items": [{"id": "x"}]}])
def test_youtube_malformed_results_fail_explicitly(payload):
    client = FakeClient(lambda url, kwargs: response(payload))
    with pytest.raises(ValueError, match="malformed YouTube"):
        collect_youtube_media(("x",), "key", client)


def test_youtube_errors_do_not_expose_api_key():
    secret = "secret-api-key"
    client = FakeClient(
        lambda url, kwargs: response({}, 403, f"{YOUTUBE_VIDEOS_URL}?key={secret}")
    )
    with pytest.raises(RuntimeError) as exc_info:
        collect_youtube_media(("x",), secret, client)
    assert secret not in str(exc_info.value)
    assert exc_info.value.__context__ is None


def test_youtube_media_search_uses_relevance_bound_and_enriches_discovered_ids(monkeypatch):
    payload = {"items": [{"id": {"videoId": "first"}}, {"id": {"videoId": "second"}}]}
    client = FakeClient(lambda url, kwargs: response(payload))
    captured = {}

    def fake_enrich(ids, api_key, passed_client):
        captured.update(ids=ids, api_key=api_key, client=passed_client)
        now = acquisition._utcnow()
        return acquisition.MediaAcquisitionResult(started_at=now, completed_at=now, candidates=())

    monkeypatch.setattr(acquisition, "collect_youtube_media", fake_enrich)
    search_youtube_media("arbitrary story", "secret-key", 7, client)

    url, kwargs = client.calls[0]
    assert url == YOUTUBE_SEARCH_URL
    assert kwargs["params"]["order"] == "relevance"
    assert kwargs["params"]["type"] == "video"
    assert kwargs["params"]["maxResults"] == 7
    assert kwargs["params"]["regionCode"] == "KR"
    assert kwargs["params"]["relevanceLanguage"] == "ko"
    assert captured == {"ids": ("first", "second"), "api_key": "secret-key", "client": client}


@pytest.mark.parametrize("count", [0, 51, True])
def test_youtube_media_search_rejects_unbounded_counts(count):
    with pytest.raises(ValueError, match="between 1 and 50"):
        search_youtube_media("query", "key", count, FakeClient(None))


def test_youtube_media_search_errors_do_not_expose_api_key():
    secret = "search-secret-key"
    client = FakeClient(
        lambda url, kwargs: response({}, 403, f"{YOUTUBE_SEARCH_URL}?key={secret}")
    )
    with pytest.raises(RuntimeError) as exc_info:
        search_youtube_media("query", secret, client=client)
    assert secret not in str(exc_info.value)
    assert exc_info.value.__context__ is None


def test_wikimedia_bounded_request_and_rights_attribution_mapping():
    payload = {
        "query": {
            "pages": [
                {
                    "pageid": 42,
                    "title": "File:Subject.jpg",
                    "canonicalurl": "https://commons.wikimedia.org/wiki/File:Subject.jpg",
                    "imageinfo": [
                        {
                            "url": "https://upload.wikimedia.org/subject.jpg",
                            "mime": "image/jpeg",
                            "width": 1600,
                            "height": 900,
                            "extmetadata": {
                                "Artist": {"value": "Photographer"},
                                "Credit": {"value": "Personal archive"},
                                "LicenseShortName": {"value": "CC BY-SA 4.0"},
                                "LicenseUrl": {"value": "https://creativecommons.org/licenses/by-sa/4.0/"},
                                "UsageTerms": {"value": "Creative Commons Attribution-Share Alike 4.0"},
                                "Copyrighted": {"value": "True"},
                            },
                        }
                    ],
                }
            ]
        }
    }
    client = FakeClient(lambda url, kwargs: response(payload))
    result = search_wikimedia_commons("subject", 3, client)
    url, kwargs = client.calls[0]
    assert url == WIKIMEDIA_API_URL
    assert kwargs["params"]["gsrlimit"] == 3
    assert kwargs["params"]["gsrnamespace"] == 6
    assert kwargs["headers"]["User-Agent"].startswith("K-Signal/")
    candidate = result.candidates[0]
    assert candidate.creator == "Photographer"
    assert candidate.source == "Personal archive"
    assert candidate.license_code == "CC BY-SA 4.0"
    assert candidate.license_url.endswith("/by-sa/4.0/")
    assert candidate.usage_terms == "Creative Commons Attribution-Share Alike 4.0"
    assert candidate.rights_statement == "True"


def test_wikimedia_missing_optional_rights_remain_none():
    payload = {
        "query": {
            "pages": [{
                "pageid": 7,
                "title": "File:Plain.webm",
                "canonicalurl": "https://commons.wikimedia.org/wiki/File:Plain.webm",
                "imageinfo": [{"url": "https://upload.wikimedia.org/plain.webm", "mime": "video/webm"}],
            }]
        }
    }
    candidate = search_wikimedia_commons(
        "plain", 1, FakeClient(lambda url, kwargs: response(payload))
    ).candidates[0]
    assert candidate.media_type == "video"
    assert candidate.creator is None
    assert candidate.license_code is None
    assert candidate.license_url is None
    assert candidate.usage_terms is None
    assert candidate.rights_statement is None


def test_wikimedia_rejects_unbounded_count():
    with pytest.raises(ValueError, match="between 1 and 50"):
        search_wikimedia_commons("query", 51, FakeClient(None))


def test_openverse_anonymous_mapping_preserves_license_and_urls():
    payload = {"results": [{
        "id": "asset-id",
        "title": "Subject",
        "creator": "Creator",
        "url": "https://media.example/subject.jpg",
        "foreign_landing_url": "https://source.example/work/1",
        "thumbnail": "https://thumb.example/subject.jpg",
        "license": "by-sa",
        "license_version": "4.0",
        "license_url": "https://creativecommons.org/licenses/by-sa/4.0/",
        "source": "flickr",
        "provider": "wikimedia",
        "width": 1200,
        "height": 800,
    }]}
    client = FakeClient(lambda url, kwargs: response(payload))
    candidate = search_openverse("subject", 4, client).candidates[0]
    url, kwargs = client.calls[0]
    assert url == OPENVERSE_IMAGES_URL
    assert kwargs["params"] == {"q": "subject", "page_size": 4}
    assert "headers" not in kwargs
    assert candidate.provider_asset_id == "asset-id"
    assert candidate.source == "flickr"
    assert candidate.media_url == "https://media.example/subject.jpg"
    assert candidate.landing_url == "https://source.example/work/1"
    assert candidate.thumbnail_url == "https://thumb.example/subject.jpg"
    assert candidate.license_code == "by-sa"
    assert candidate.license_version == "4.0"
    assert candidate.license_url.endswith("/by-sa/4.0/")


def test_openverse_missing_optional_metadata_remains_none():
    payload = {"results": [{
        "id": "minimal",
        "title": None,
        "url": "https://media.example/minimal.jpg",
        "foreign_landing_url": "https://source.example/minimal",
    }]}
    candidate = search_openverse(
        "minimal", 1, FakeClient(lambda url, kwargs: response(payload))
    ).candidates[0]
    assert candidate.title is None
    assert candidate.creator is None
    assert candidate.thumbnail_url is None
    assert candidate.license_code is None
    assert candidate.width is None


def test_media_models_are_frozen_and_forbid_extra_fields():
    candidate = MediaCandidate(
        provider="openverse",
        provider_asset_id="id",
        media_type="image",
        title="title",
        media_url="https://media.example/image.jpg",
        landing_url="https://source.example/image",
    )
    with pytest.raises(ValidationError):
        candidate.title = "changed"
    with pytest.raises(ValidationError):
        MediaCandidate(**candidate.model_dump(), invented_relevance=1)


def test_editorial_video_principle_is_documented_without_provider_ranking():
    import ksignal.engine.media_acquisition as acquisition

    assert "Video does not win merely because video exists" in acquisition.__doc__
    assert not hasattr(acquisition, "rank_media")
