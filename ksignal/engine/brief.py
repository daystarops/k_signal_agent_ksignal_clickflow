from __future__ import annotations
import json
from pathlib import Path
from pydantic import BaseModel,Field
from .claims import frame_claim
from .models import Claim,SourceNode
from .roles import layer_status
from .scoring import CandidateScore

class CandidateBrief(BaseModel):
    candidate_id:str; issue_id:str; working_headline:str; lane:str; core_signal:str
    sources:list[SourceNode]=Field(default_factory=list); claims:list[Claim]=Field(default_factory=list)
    scores:CandidateScore=Field(default_factory=CandidateScore); temporal_movement:str="Baseline established"
    signal_velocity:str="unknown"; operational_gaps:list[str]=Field(default_factory=list); next_capture_actions:list[str]=Field(default_factory=list)
    @property
    def recommendation(self):
        layers=layer_status(self.sources)
        if self.scores.auto_queue_eligible:return "USE"
        if self.scores.total_weighted>=5 or "missing" in layers.values():return "HOLD"
        if self.scores.total_weighted>0:return "RESEARCH"
        return "REJECT"

def render_brief(brief:CandidateBrief):
    layers=layer_status(brief.sources); by_role=lambda r:[s for s in brief.sources if any(x.value==r for x in s.source_roles)]
    claims="\n".join(f"| {frame_claim(c, platform=(brief.sources[0].platform if brief.sources else 'Platform'))} | {c.confidence_grade.value} | {c.classification} | {', '.join(c.supporting_source_ids)} |" for c in brief.claims) or "| No claims | D | discourse | |"
    src="\n".join(f"- {s.source_id}: {s.url} ({s.current_access_status.value})" for s in brief.sources) or "- None"
    return f"""# Candidate Signal Brief

## Working Headline
{brief.working_headline}

## Lane
{brief.lane}

## Core Signal
{brief.core_signal}

## Korean-Native Signal
{layers['korean_native']}

## Official Context
{layers['official']}

## Western/Global Mirror
{layers['western_global']}

## Instagram/Social Mirror
{layers['instagram_social']}

## Frame Differential
Pending correlation.

## Internet Discourse Summary
{brief.core_signal}

## Claims Register
| Claim | Confidence | Classification | Sources |
|---|---|---|---|
{claims}

## Visual/Creative Opportunities
{layers['creative_reference']}

## Source Graph
{src}

## Scores
- Total Weighted: {brief.scores.total_weighted}
- Auto-Queue Eligible: {str(brief.scores.auto_queue_eligible).lower()}

## Temporal Movement
{brief.temporal_movement}

## Signal Velocity
{brief.signal_velocity}

## Operational Gaps
{chr(10).join('- '+x for x in brief.operational_gaps) or '- None'}

## Next Capture Actions
{chr(10).join('- '+x for x in brief.next_capture_actions) or '- Recapture on schedule'}

## Recommendation
{brief.recommendation}
"""

def write_brief(brief,path):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True); path.write_text(render_brief(brief),encoding="utf-8"); path.with_suffix(".json").write_text(brief.model_dump_json(indent=2),encoding="utf-8"); return path
