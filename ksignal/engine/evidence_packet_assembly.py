from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from ksignal.engine.evidence import (
    CollectionRun,
    EvidenceLane,
    EvidencePacket,
    EvidenceQuery,
    EvidenceRecord,
    EvidenceSubject,
    SearchContextRef,
    SearchWake,
)
from ksignal.engine.models import AccessStatus
from ksignal.engine.source_collectors import (
    GoogleWakeCandidate,
    NewsisCollection,
    YouTubeCollection,
)
from ksignal.engine.wake_classifier import WakeLane, WakeLaneClassification


PACKET_QUERY_WAKE_MISMATCH = "PACKET_QUERY_WAKE_MISMATCH"
WAKE_LANE_QUERY_MISMATCH = "WAKE_LANE_QUERY_MISMATCH"
OUT_OF_SCOPE_WAKE_CANNOT_BUILD_PACKET = "OUT_OF_SCOPE_WAKE_CANNOT_BUILD_PACKET"


def assemble_evidence_packet(
    *,
    packet_id: str,
    packet_revision: int,
    issue_id: str,
    candidate_id: str,
    packet_created_at: datetime,
    subject: EvidenceSubject,
    query: EvidenceQuery,
    wake: GoogleWakeCandidate,
    lane_classification: WakeLaneClassification,
    newsis_collection: NewsisCollection,
    youtube_collection: YouTubeCollection,
    newsis_run_id: str,
    youtube_run_id: str,
    evidence: Sequence[EvidenceRecord],
) -> EvidencePacket:
    if query.original != wake.query:
        raise ValueError(PACKET_QUERY_WAKE_MISMATCH)
    if lane_classification.query != wake.query:
        raise ValueError(WAKE_LANE_QUERY_MISMATCH)
    if lane_classification.lane == WakeLane.OUT_OF_SCOPE:
        raise ValueError(OUT_OF_SCOPE_WAKE_CANNOT_BUILD_PACKET)

    lane = EvidenceLane(lane_classification.lane.value)
    search_wake = SearchWake(
        provider=wake.provider,
        geo=wake.geo,
        observed_at=wake.observed_at,
        approx_traffic_raw=wake.approx_traffic_raw,
        approx_traffic_floor=wake.approx_traffic_floor,
        context_refs=tuple(
            SearchContextRef(title=ref.title, source=ref.source, url=ref.url)
            for ref in wake.context_refs
        ),
    )
    evidence_tuple = tuple(evidence)
    newsis_run = CollectionRun(
        run_id=newsis_run_id,
        provider="newsis",
        operation="collect_newsis_pool",
        status=AccessStatus.CAPTURED,
        failure_mode=None,
        started_at=newsis_collection.started_at,
        completed_at=newsis_collection.completed_at,
        raw_item_count=len(newsis_collection.items),
        relevant_item_count=sum(record.provider == "newsis" for record in evidence_tuple),
    )
    youtube_run = CollectionRun(
        run_id=youtube_run_id,
        provider="youtube",
        operation="collect_youtube_search",
        status=AccessStatus.CAPTURED,
        failure_mode=None,
        started_at=youtube_collection.started_at,
        completed_at=youtube_collection.completed_at,
        raw_item_count=len(youtube_collection.items),
        relevant_item_count=sum(record.provider == "youtube" for record in evidence_tuple),
    )
    return EvidencePacket(
        schema_version="evidence_packet.v0.1",
        packet_id=packet_id,
        packet_revision=packet_revision,
        issue_id=issue_id,
        candidate_id=candidate_id,
        lane=lane,
        subject=subject,
        query=query,
        search_wake=search_wake,
        collection_runs=(newsis_run, youtube_run),
        evidence=evidence_tuple,
        packet_created_at=packet_created_at,
    )
