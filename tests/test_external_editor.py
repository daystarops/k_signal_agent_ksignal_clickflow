from __future__ import annotations

import json
from copy import deepcopy
from io import BytesIO
from urllib.error import HTTPError

import pytest

import ksignal.external_editor as external
from ksignal.editorial_writer import EditorialWriterOutput
from ksignal.external_editor import ExternalEditorError, edit_external_draft


def _draft(section_count: int = 3) -> EditorialWriterOutput:
    data = {
        "headline": "Im Ji-min’s Update — 임지민",
        "dek": "The statement called it a “facial contusion”.",
        "internet_read": "임지민 returned later that day.",
        "sections": [
            {"heading": f"Part {number}", "body": f"Exact body {number}."}
            for number in range(section_count)
        ],
    }
    if section_count > 4:
        return EditorialWriterOutput.model_construct(
            **{**data, "sections": data["sections"]}
        )
    return EditorialWriterOutput.model_validate(data)


def _review(draft: EditorialWriterOutput, *, notes: int = 1, sections: int | None = None) -> dict:
    return {
        "headline": draft.headline,
        "dek": draft.dek,
        "internet_read": draft.internet_read,
        "sections": [
            {"heading": f"Edited {number}", "body": f"Edited body {number}."}
            for number in range(sections if sections is not None else len(draft.sections))
        ],
        "editor_notes": [
            {"original": "Exact", "reason": "Tighter", "change": "Edited"}
            for _ in range(notes)
        ],
    }


class _Response:
    status = 200

    def __init__(self, result: dict):
        self.body = json.dumps(
            {"choices": [{"message": {"content": json.dumps(result, ensure_ascii=False)}}]},
            ensure_ascii=False,
        ).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def getcode(self):
        return self.status

    def read(self):
        return self.body


def _install(monkeypatch: pytest.MonkeyPatch, draft: EditorialWriterOutput, result: dict | None = None):
    captured = {}

    def fake_urlopen(request):
        captured["request"] = request
        return _Response(result or _review(draft))

    monkeypatch.setenv("WRITER_API_KEY", "secret-writer-key")
    monkeypatch.setattr(external, "urlopen", fake_urlopen)
    return captured


def test_request_endpoint_auth_model_schema_exact_content_and_public_boundary(monkeypatch):
    draft = _draft()
    captured = _install(monkeypatch, draft)
    edit_external_draft(draft)
    request = captured["request"]
    payload = json.loads(request.data.decode("utf-8"))

    assert request.full_url == "https://api.writer.com/v1/chat"
    assert request.get_header("Authorization") == "Bearer secret-writer-key"
    assert request.get_header("User-agent") == "K-Signal/1.0 ExternalEditor"
    assert "Python-urllib" not in request.get_header("User-agent")
    assert "secret-writer-key" not in request.data.decode("utf-8")
    assert payload["model"] == "palmyra-x5"
    assert payload["response_format"]["type"] == "json_schema"
    assert payload["response_format"]["json_schema"]["strict"] is True
    supplied = json.loads(payload["messages"][1]["content"].split("\n", 1)[1])
    assert supplied == draft.model_dump()
    prompt = json.dumps(payload["messages"], ensure_ascii=False).lower()
    for forbidden in (
        "repository",
        "evidence",
        "business_read",
        "pass/hold/fail",
        "scoring",
    ):
        assert forbidden not in prompt


def test_section_count_must_match_and_more_than_four_input_fails(monkeypatch):
    draft = _draft()
    _install(monkeypatch, draft, _review(draft, sections=2))
    with pytest.raises(ExternalEditorError, match="section count"):
        edit_external_draft(draft)
    with pytest.raises(ExternalEditorError, match="more than 4"):
        edit_external_draft(_draft(5))


def test_more_than_five_editor_notes_fails(monkeypatch):
    draft = _draft()
    _install(monkeypatch, draft, _review(draft, notes=6))
    with pytest.raises(ExternalEditorError, match="failed validation"):
        edit_external_draft(draft)


def test_draft_is_unchanged_and_utf8_survives_round_trip(monkeypatch):
    draft = _draft()
    before = deepcopy(draft)
    captured = _install(monkeypatch, draft)
    review = edit_external_draft(draft)

    assert draft == before
    assert review.headline == "Im Ji-min’s Update — 임지민"
    assert review.dek == "The statement called it a “facial contusion”."
    request_text = captured["request"].data.decode("utf-8")
    for text in ("Im Ji-min’s", "“facial contusion”", "임지민"):
        assert text in request_text


def test_missing_key_fails_clearly(monkeypatch):
    monkeypatch.delenv("WRITER_API_KEY", raising=False)
    with pytest.raises(ExternalEditorError, match="WRITER_API_KEY"):
        edit_external_draft(_draft())


def test_malformed_response_fails_clearly(monkeypatch):
    draft = _draft()
    monkeypatch.setenv("WRITER_API_KEY", "secret")
    response = _Response(_review(draft))
    response.body = b"not json"
    monkeypatch.setattr(external, "urlopen", lambda _request: response)
    with pytest.raises(ExternalEditorError, match="malformed response"):
        edit_external_draft(draft)


def test_http_error_includes_sanitized_provider_detail(monkeypatch):
    draft = _draft()
    monkeypatch.setenv("WRITER_API_KEY", "secret-writer-key")
    error_body = json.dumps(
        {
            "title": "Error 1010: Access denied",
            "detail": "The site owner blocked this browser signature.",
        }
    ).encode("utf-8")

    def fail(_request):
        raise HTTPError(
            external.WRITER_CHAT_URL,
            403,
            "Forbidden",
            {"Content-Type": "application/json"},
            BytesIO(error_body),
        )

    monkeypatch.setattr(external, "urlopen", fail)
    with pytest.raises(
        ExternalEditorError,
        match=r"^Writer API returned HTTP 403: Error 1010: Access denied$",
    ) as captured:
        edit_external_draft(draft)
    assert "secret-writer-key" not in str(captured.value)
