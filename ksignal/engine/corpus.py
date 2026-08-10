from __future__ import annotations
import json,shutil
from pathlib import Path
from .brief import CandidateBrief,render_brief
from .models import Claim,ConfidenceGrade,SourceNode,SourceRole,SourceType
from .scoring import CandidateScore
CARDS={"card_01":("Global K-pop fandom tension","fandom"),"card_02":("Billlie / Work / Zap","fandom"),"card_03":("K League starter pack","sports"),"card_04":("Lingard / FC Seoul","sports")}
def generate_issue_001(output_root="outputs"):
    root=Path(output_root)/"issues"/"001"/"source_engine_test"; root.mkdir(parents=True,exist_ok=True); made=[]
    for cid,(headline,lane) in CARDS.items():
        node=SourceNode(issue_id="001",candidate_id=cid,url=f"corpus://issue-001/{cid}",platform="issue_001",title=headline,source_roles=[SourceRole.ORIGIN_SIGNAL],source_type=SourceType.UNKNOWN,current_access_status="captured",summary="Existing Issue 001 corpus baseline")
        claim=Claim(claim_text=f"Issue 001 contains the {headline} signal.",supporting_source_ids=[node.source_id],confidence=6,confidence_grade=ConfidenceGrade.C,classification="fact",scope="specific")
        score=CandidateScore(cultural_signal_strength=7,korean_source_quality=5,cross_correlation=4,signal_noise_ratio=7,lane_fit=8,freshness=2)
        brief=CandidateBrief(candidate_id=cid,issue_id="001",working_headline=headline,lane=lane,core_signal="Historical corpus baseline; recapture required.",sources=[node],claims=[claim],scores=score,operational_gaps=["Official, western/global, Instagram, and visual layers require recapture"],next_capture_actions=["Discover current public mirrors"])
        graph={"candidate_id":cid,"sources":[node.model_dump(mode="json")],"layers":{"korean_native":"present","official":"missing","western_global":"missing","instagram_social":"missing","creative_reference":"missing"},"temporal_baseline":True,"score":score.model_dump()}; (root/f"{cid}_source_graph.json").write_text(json.dumps(graph,indent=2),encoding="utf-8"); (root/f"{cid}_brief.md").write_text(render_brief(brief),encoding="utf-8"); (root/f"{cid}_creative_manifest.json").write_text(json.dumps({"candidate_id":cid,"render_targets":["article_visual","source_receipt","quote_card","context_card","velocity_card","instagram_card","western_mirror_card","reel_edl"],"status":"planned"},indent=2),encoding="utf-8"); made.append(cid)
    (root/"ISSUE_001_AUDIT.md").write_text("# Issue 001 Source Engine Audit\n\nFour cards processed as an immutable corpus. Public HTML was not modified.\n",encoding="utf-8"); return made

