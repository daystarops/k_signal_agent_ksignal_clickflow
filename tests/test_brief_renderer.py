from ksignal.engine.brief import CandidateBrief,render_brief
from ksignal.engine.models import Claim
def test_claims_register():
    b=CandidateBrief(candidate_id="c",issue_id="1",working_headline="h",lane="fandom",core_signal="s",claims=[Claim(claim_text="x",confidence=5,confidence_grade="D",classification="discourse",scope="trend")]); out=render_brief(b); assert "## Claims Register" in out and "discourse suggests" in out and "Total Weighted" in out

