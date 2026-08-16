from __future__ import annotations

import html
import math
import unicodedata
from datetime import datetime, timezone
from enum import Enum
from html.parser import HTMLParser
from typing import Any, Sequence

from pydantic import BaseModel, ConfigDict

from ksignal.engine.source_collectors import GoogleWakeCandidate, NewsisItem


DEFAULT_NEWSIS_NARROWING_MODEL = "text-embedding-3-small"
NEWSIS_LITERAL_TOP_K = 3
NEWSIS_SEMANTIC_TOP_K = 3
NEWSIS_MAX_CANDIDATES = 6
NEWSIS_EMBEDDING_DESCRIPTION_MAX_CHARS = 3_000


class _FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class NewsisCandidateSelection(str, Enum):
    LITERAL = "literal"
    SEMANTIC = "semantic"
    LITERAL_AND_SEMANTIC = "literal_and_semantic"


class NewsisNarrowedCandidate(_FrozenModel):
    url: str
    feeds: tuple[str, ...]
    title: str
    description: str
    published_at_raw: str
    literal_match: bool
    semantic_score: float
    selected_by: NewsisCandidateSelection


class NewsisWakeNarrowingResult(_FrozenModel):
    query: str
    raw_item_count: int
    deduped_item_count: int
    literal_match_count: int
    candidates: tuple[NewsisNarrowedCandidate, ...]


class NewsisCandidateNarrowingBatch(_FrozenModel):
    results: tuple[NewsisWakeNarrowingResult, ...]
    requested_model: str
    actual_model: str | None
    narrowed_at: datetime


class _DedupedItem:
    def __init__(self, item: NewsisItem) -> None:
        self.item = item
        self.feeds = [item.feed]


class _HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def _normalize_literal(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    return "".join(character for character in normalized if character.isalnum())


def _semantic_description(description: str) -> str:
    parser = _HTMLTextExtractor()
    parser.feed(html.unescape(description))
    parser.close()
    cleaned = " ".join("".join(parser.parts).split())
    return cleaned[:NEWSIS_EMBEDDING_DESCRIPTION_MAX_CHARS]


def _document_text(item: NewsisItem) -> str:
    return (
        f"NEWS ARTICLE\nTITLE: {item.title}\n"
        f"DESCRIPTION: {_semantic_description(item.description)}"
    )


def _wake_text(wake: GoogleWakeCandidate) -> str:
    if not wake.context_refs:
        return f"GOOGLE SEARCH WAKE\nQUERY: {wake.query}\nGOOGLE CONTEXT: none"
    context = "\n".join(
        f"{index}. [{reference.source}] {reference.title}"
        for index, reference in enumerate(wake.context_refs, start=1)
    )
    return f"GOOGLE SEARCH WAKE\nQUERY: {wake.query}\nGOOGLE CONTEXT:\n{context}"


def _cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right):
        raise ValueError("embedding dimensions do not match")
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return sum(a * b for a, b in zip(left, right)) / (left_norm * right_norm)


def _dedupe(items: Sequence[NewsisItem]) -> tuple[_DedupedItem, ...]:
    by_url: dict[str, _DedupedItem] = {}
    for item in items:
        existing = by_url.get(item.url)
        if existing is None:
            by_url[item.url] = _DedupedItem(item)
        elif item.feed not in existing.feeds:
            existing.feeds.append(item.feed)
    return tuple(by_url.values())


def narrow_newsis_candidates(
    *,
    wakes: Sequence[GoogleWakeCandidate],
    items: Sequence[NewsisItem],
    client: Any,
    model: str = DEFAULT_NEWSIS_NARROWING_MODEL,
) -> NewsisCandidateNarrowingBatch:
    wakes = tuple(wakes)
    raw_items = tuple(items)
    deduped = _dedupe(raw_items)

    if not wakes or not deduped:
        results = tuple(
            NewsisWakeNarrowingResult(
                query=wake.query,
                raw_item_count=len(raw_items),
                deduped_item_count=len(deduped),
                literal_match_count=0,
                candidates=(),
            )
            for wake in wakes
        )
        return NewsisCandidateNarrowingBatch(
            results=results,
            requested_model=model,
            actual_model=None,
            narrowed_at=datetime.now(timezone.utc),
        )

    embedding_input = [entry for entry in (_document_text(value.item) for value in deduped)]
    embedding_input.extend(_wake_text(wake) for wake in wakes)
    response = client.embeddings.create(model=model, input=embedding_input)
    data = tuple(response.data)
    if len(data) != len(embedding_input):
        raise ValueError(
            f"embedding output count mismatch: expected {len(embedding_input)}, got {len(data)}"
        )
    vectors = tuple(tuple(value.embedding) for value in data)
    document_vectors = vectors[: len(deduped)]
    wake_vectors = vectors[len(deduped) :]

    results: list[NewsisWakeNarrowingResult] = []
    normalized_documents = tuple(
        _normalize_literal(f"{value.item.title}{value.item.description}") for value in deduped
    )
    for wake, wake_vector in zip(wakes, wake_vectors):
        normalized_query = _normalize_literal(wake.query)
        literal_flags = tuple(
            bool(normalized_query) and normalized_query in document
            for document in normalized_documents
        )
        scores = tuple(
            _cosine_similarity(wake_vector, document_vector)
            for document_vector in document_vectors
        )
        ranked_all = sorted(range(len(deduped)), key=lambda i: (-scores[i], deduped[i].item.url))
        literal = [index for index in ranked_all if literal_flags[index]][:NEWSIS_LITERAL_TOP_K]
        semantic = ranked_all[:NEWSIS_SEMANTIC_TOP_K]
        semantic_set = set(semantic)
        selected = literal + [index for index in semantic if index not in set(literal)]
        candidates = tuple(
            NewsisNarrowedCandidate(
                url=deduped[index].item.url,
                feeds=tuple(deduped[index].feeds),
                title=deduped[index].item.title,
                description=deduped[index].item.description,
                published_at_raw=deduped[index].item.published_at_raw,
                literal_match=literal_flags[index],
                semantic_score=scores[index],
                selected_by=(
                    NewsisCandidateSelection.LITERAL_AND_SEMANTIC
                    if index in semantic_set and index in literal
                    else NewsisCandidateSelection.LITERAL
                    if index in literal
                    else NewsisCandidateSelection.SEMANTIC
                ),
            )
            for index in selected[:NEWSIS_MAX_CANDIDATES]
        )
        results.append(
            NewsisWakeNarrowingResult(
                query=wake.query,
                raw_item_count=len(raw_items),
                deduped_item_count=len(deduped),
                literal_match_count=sum(literal_flags),
                candidates=candidates,
            )
        )

    narrowed_at = datetime.now(timezone.utc)
    return NewsisCandidateNarrowingBatch(
        results=tuple(results),
        requested_model=model,
        actual_model=getattr(response, "model", None),
        narrowed_at=narrowed_at,
    )
