"""Advisory second-opinion editing through Writer's Palmyra API."""

from __future__ import annotations

import json
import os
from typing import Annotated, Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError

from .editorial_writer import EditorialWriterOutput, WriterSection


WRITER_CHAT_URL = "https://api.writer.com/v1/chat"
NonEmptyStr = Annotated[str, StringConstraints(min_length=1)]


class ExternalEditorError(RuntimeError):
    """Raised when an external editorial review cannot be obtained safely."""


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ExternalEditorNote(_StrictModel):
    original: NonEmptyStr
    reason: NonEmptyStr
    change: NonEmptyStr


class ExternalEditorialReview(_StrictModel):
    headline: NonEmptyStr
    dek: NonEmptyStr
    internet_read: NonEmptyStr
    sections: list[WriterSection] = Field(min_length=1, max_length=4)
    editor_notes: list[ExternalEditorNote] = Field(max_length=5)


_EDITORIAL_DOCTRINE = """You are the second editor on a reported publication article.

Edit the supplied draft without adding facts, reporting, inference,
background knowledge, or new claims.

The publication voice is restrained, observant, human, and emotionally
aware without announcing its emotions.

Preserve emotion already present in the reporting.
Do not manufacture it.

Prefer concrete facts, actions, timing, and human behavior over abstract
interpretation.

Remove or rewrite prose that feels:
- machine-composed
- ornamental
- self-consciously literary
- unnecessarily explanatory
- abstract when a concrete fact already makes the point
- written mainly to sound clever

Do not:
- make the story more dramatic
- add metaphors
- manufacture a final line
- tell the reader what to feel
- add outside context
- strengthen factual claims
- convert 'did not open immediately' into 'locked'
- add a conclusion merely because articles conventionally have one

Preserve the supplied number of article sections.

The 'What the Internet Is Really Saying' field is not an article summary.
Keep it focused on the consequential or revealing detail that could be
lost in headline-level consumption.

Return a revised draft and up to five concrete editor notes."""


def _response_schema() -> dict[str, Any]:
    schema = ExternalEditorialReview.model_json_schema()
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "external_editorial_review",
            "strict": True,
            "schema": schema,
        },
    }


def _extract_review(response_data: Any) -> Any:
    try:
        content = response_data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ExternalEditorError("Writer returned a malformed response") from exc
    if isinstance(content, str):
        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:
            raise ExternalEditorError("Writer returned malformed structured output") from exc
    if isinstance(content, dict):
        return content
    raise ExternalEditorError("Writer returned malformed structured output")


def edit_external_draft(
    draft: EditorialWriterOutput,
    model: str = "palmyra-x5",
) -> ExternalEditorialReview:
    """Request an advisory copy edit of a completed Draft A."""
    api_key = os.getenv("WRITER_API_KEY")
    if not api_key:
        raise ExternalEditorError("WRITER_API_KEY is required for external editorial review")
    if len(draft.sections) > 4:
        raise ExternalEditorError("Draft A cannot contain more than 4 sections")

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": _EDITORIAL_DOCTRINE},
            {
                "role": "user",
                "content": "DRAFT A (article copy to edit):\n"
                + json.dumps(draft.model_dump(), ensure_ascii=False, indent=2),
            },
        ],
        "response_format": _response_schema(),
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = Request(
        WRITER_CHAT_URL,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "application/json",
        },
        method="POST",
    )

    try:
        with urlopen(request) as response:
            status = getattr(response, "status", None)
            if status is None:
                status = response.getcode()
            raw_response = response.read()
    except HTTPError as exc:
        raise ExternalEditorError(f"Writer API returned HTTP {exc.code}") from exc
    except (URLError, OSError) as exc:
        raise ExternalEditorError("Writer API request failed") from exc
    if not 200 <= status < 300:
        raise ExternalEditorError(f"Writer API returned HTTP {status}")

    try:
        response_data = json.loads(raw_response.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ExternalEditorError("Writer returned a malformed response") from exc
    try:
        review = ExternalEditorialReview.model_validate(_extract_review(response_data))
    except ValidationError as exc:
        raise ExternalEditorError("Writer structured output failed validation") from exc
    if len(review.sections) != len(draft.sections):
        raise ExternalEditorError(
            "Writer structured output changed the Draft A section count"
        )
    return review
