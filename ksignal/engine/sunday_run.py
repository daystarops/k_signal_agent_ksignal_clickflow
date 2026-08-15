from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

import httpx

from ksignal.engine.candidate_preparation import (
    NewsisCandidateBinding,
    prepare_newsis_candidates,
    prepare_youtube_candidates,
)
from ksignal.engine.evidence import EvidenceAssessment, EvidencePacket, EvidenceQuery, EvidenceSubject
from ksignal.engine.evidence_assessment_judge import judge_evidence_packet
from ksignal.engine.evidence_packet_assembly import assemble_evidence_packet
from ksignal.engine.evidence_record_bridge import EvidenceCollectionContext, build_evidence_records
from ksignal.engine.independence_classifier import classify_candidate_independence
from ksignal.engine.newsis_candidate_narrowing import narrow_newsis_candidates
from ksignal.engine.relevance_classifier import RelevanceProvider, classify_candidate_relevance
from ksignal.engine.source_collectors import (
    GoogleWakeCandidate,
    collect_newsis_pool,
    collect_youtube_search,
)
from ksignal.engine.wake_classifier import (
    WakeLane,
    WakeLaneClassification,
    classify_wake_lanes,
)


class MissingNewsisCandidateIds(ValueError):
    def __init__(self, urls: tuple[str, ...]) -> None:
        self.urls = urls
        super().__init__(", ".join(urls))


@dataclass(frozen=True)
class SundayOutOfScopeResult:
    lane_classification: WakeLaneClassification
    status: Literal["out_of_scope"] = field(default="out_of_scope", init=False)


@dataclass(frozen=True)
class SundayAssessedResult:
    lane_classification: WakeLaneClassification
    packet: EvidencePacket
    assessment: EvidenceAssessment
    status: Literal["assessed"] = field(default="assessed", init=False)


SundayRunResult = SundayOutOfScopeResult | SundayAssessedResult


def run_selected_wake(
    *,
    wake: GoogleWakeCandidate,
    subject: EvidenceSubject,
    query: EvidenceQuery,
    youtube_published_after: datetime,
    newsis_candidate_ids_by_url: Mapping[str, str],
    issue_id: str,
    candidate_id: str,
    packet_id: str,
    packet_revision: int,
    packet_created_at: datetime,
    newsis_run_id: str,
    youtube_run_id: str,
    openai_client: Any,
    youtube_api_key: str,
    http_client: httpx.Client | None = None,
    lane_model: str = "gpt-5-mini",
    narrowing_model: str = "text-embedding-3-small",
    relevance_model: str = "gpt-5-mini",
    independence_model: str = "gpt-5-mini",
    assessment_model: str = "gpt-5-mini",
) -> SundayRunResult:
    lane_batch = classify_wake_lanes((wake,), openai_client, model=lane_model)
    if len(lane_batch.classifications) != 1:
        raise ValueError("selected wake must have exactly one lane classification")
    classification = lane_batch.classifications[0]
    if classification.query != wake.query:
        raise ValueError("lane classification query must match selected wake exactly")
    if classification.lane == WakeLane.OUT_OF_SCOPE:
        return SundayOutOfScopeResult(lane_classification=classification)

    newsis_collection = collect_newsis_pool(client=http_client)
    youtube_collection = collect_youtube_search(
        wake.query,
        youtube_published_after,
        youtube_api_key,
        client=http_client,
    )
    narrowing_batch = narrow_newsis_candidates(
        wakes=(wake,),
        items=newsis_collection.items,
        client=openai_client,
        model=narrowing_model,
    )
    if len(narrowing_batch.results) != 1:
        raise ValueError("selected wake must have exactly one Newsis narrowing result")
    narrowing = narrowing_batch.results[0]
    if narrowing.query != wake.query:
        raise ValueError("Newsis narrowing query must match selected wake exactly")

    missing_urls = tuple(
        narrowed.url
        for narrowed in narrowing.candidates
        if narrowed.url not in newsis_candidate_ids_by_url
    )
    if missing_urls:
        raise MissingNewsisCandidateIds(missing_urls)
    bindings = tuple(
        NewsisCandidateBinding(
            candidate_id=newsis_candidate_ids_by_url[narrowed.url],
            narrowed=narrowed,
        )
        for narrowed in narrowing.candidates
    )

    prepared_newsis = prepare_newsis_candidates(
        bindings=bindings,
        collection=newsis_collection,
    )
    prepared_youtube = prepare_youtube_candidates(collection=youtube_collection)
    prepared = prepared_newsis + prepared_youtube
    relevance_candidates = tuple(item.source.candidate for item in prepared)
    relevance_batch = classify_candidate_relevance(
        wake,
        relevance_candidates,
        openai_client,
        model=relevance_model,
    )

    relevant_ids = {
        result.candidate_id for result in relevance_batch.results if result.relevant
    }
    relevant_independence_candidates = tuple(
        item.independence_candidate
        for item in prepared
        if item.independence_candidate.candidate_id in relevant_ids
    )
    independence_batch = classify_candidate_independence(
        candidates=relevant_independence_candidates,
        client=openai_client,
        model=independence_model,
    )

    collection_contexts = (
        EvidenceCollectionContext(
            provider=RelevanceProvider.NEWSIS,
            run_id=newsis_run_id,
            completed_at=newsis_collection.completed_at,
        ),
        EvidenceCollectionContext(
            provider=RelevanceProvider.YOUTUBE,
            run_id=youtube_run_id,
            completed_at=youtube_collection.completed_at,
        ),
    )
    evidence = build_evidence_records(
        sources=tuple(item.source for item in prepared),
        relevance_results=relevance_batch.results,
        independence_assignments=independence_batch.results,
        collection_contexts=collection_contexts,
    )
    packet = assemble_evidence_packet(
        packet_id=packet_id,
        packet_revision=packet_revision,
        issue_id=issue_id,
        candidate_id=candidate_id,
        packet_created_at=packet_created_at,
        subject=subject,
        query=query,
        wake=wake,
        lane_classification=classification,
        newsis_collection=newsis_collection,
        youtube_collection=youtube_collection,
        newsis_run_id=newsis_run_id,
        youtube_run_id=youtube_run_id,
        evidence=evidence,
    )
    assessment = judge_evidence_packet(
        packet=packet,
        client=openai_client,
        model=assessment_model,
    )
    return SundayAssessedResult(
        lane_classification=classification,
        packet=packet,
        assessment=assessment,
    )
