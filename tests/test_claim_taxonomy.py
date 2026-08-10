import pytest
from ksignal.engine.models import Claim,ConfidenceGrade
from ksignal.engine.claims import frame_claim
def claim(g): return Claim(claim_text="Signal exists.",confidence=5,confidence_grade=g,classification="fact",scope="specific")
def test_frames():
    assert frame_claim(claim(ConfidenceGrade.A)).startswith("Multiple sources confirm")
    assert frame_claim(claim(ConfidenceGrade.B),source="Agency").startswith("Agency states")
    assert frame_claim(claim(ConfidenceGrade.C),platform="Instagram").startswith("Instagram users report")
    assert frame_claim(claim(ConfidenceGrade.D),platform="Forum").startswith("Forum discourse suggests")
def test_taxonomy():
    with pytest.raises(ValueError): Claim(claim_text="x",confidence=1,classification="risk",scope="specific")

